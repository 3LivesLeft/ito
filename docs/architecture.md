# Architecture

Status: **Proposed — revised after independent review** · No application code exists yet. This
describes the intended structure so that Phase 1 can be reviewed against it.

Evidence and reasoning: [feasibility study](research/feasibility.md),
[ADR 0001](adr/0001-networking-foundation.md), [threat model](security/threat-model.md),
[first-run UX](ux/first-run.md).

## 1. Goals that shape the architecture

1. **Easy to use.** Safe defaults; a handful of plainly named options; status messages written for
   people ([first-run UX](ux/first-run.md)).
2. **Reuse upstream.** RNS (and later LXMF) do all protocol work. MeshBeacon configures,
   supervises, observes and explains.
3. **Separate the core from Home Assistant.** The core must run, and be tested, without Home
   Assistant (and in v1.0 as standalone Docker).
4. **Least privilege.** No host network, no HA/Supervisor API access, no extra capabilities,
   non-root service user, custom AppArmor profile. A Supervisor security rating of 8 is a
   **target that reflects these choices, not evidence of security**.
5. **Fail safe and recover.** Losing connectivity, a crashed RNS process or a corrupt cache must
   never take down Home Assistant or silently change the node's identity.
6. **Small and readable.** A competent reviewer should be able to read the whole core in a
   sitting.

## 2. Component overview (v0.1.0)

```text
┌──────────────────────────── Home Assistant OS host ────────────────────────────┐
│  Supervisor ── watchdog: HTTP GET → container IP:health port (every 120 s)     │
│                                                                                │
│  ┌──────────────── MeshBeacon app container (bridged network) ──────────────┐  │
│  │  s6-overlay (PID 1, root)                                                │  │
│  │   └─ init (root, once): validate options, umask 077, prepare /data,      │  │
│  │      chown to meshbeacon user, validate identity, render RNS config      │  │
│  │   └─ meshbeacon-core (user: meshbeacon)                                  │  │
│  │        ├─ process supervisor (back-off, circuit breaker, guards)         │  │
│  │        ├─ health endpoint (process health only, internal port)           │  │
│  │        ├─ status reporter (plain-language log lines)                     │  │
│  │        └─ RNS child process (user: meshbeacon)                           │  │
│  │              /data/reticulum  (0700)                                     │  │
│  └───────────────────────────────────────┬──────────────────────────────────┘  │
└──────────────────────────────────────────┼─────────────────────────────────────┘
                                           │ outbound TCP only
                                           ▼
                 user-chosen peers: verified presets and/or custom peers (none by default)
```

v0.2 adds the HA integration and a token-authenticated local API (§7); v0.1 has neither.

## 3. Layers and packages

| Layer | Package (proposed) | Depends on HA? | Responsibility |
|---|---|---|---|
| **Core** | `meshbeacon` (Python) | **No** | Settings validation; injection-safe RNS config rendering; identity management; RNS child-process supervision; health model; status reporting; resource guards. |
| **App adapter** | `app/` (Dockerfile, `config.yaml`, s6 service definitions, `apparmor.txt`, translations, `DOCS.md`) | Yes (Supervisor) | Map `/data/options.json` → core settings; privilege drop; start core. Contains **no business logic**. |
| **Integration** (v0.2+) | `custom_components/meshbeacon` | Yes (HA Core) | Entities, repairs, diagnostics via the core's local API. Never imports `RNS`. |
| **Standalone** (v1.0) | `docker/` | No | Same core, configured from a file or environment variables. |

Rules: the core never imports `homeassistant` or `bashio`; the integration never imports `RNS` or
`LXMF`; all cross-layer communication uses one versioned, schema-validated interface.

## 4. Core internals

### 4.1 Settings validation and injection-safe configuration rendering

RNS reads its configuration with a vendored **ConfigObj** parser (`RNS/vendor/configobj.py`).
**[Verified by test]** naive string templating of user input into that format is exploitable:

| Input in a "host" field | Effect when templated naively |
|---|---|
| `peer.example\n  [[Injected]]\n    type = AutoInterface …` | A **new interface is created** (here, LAN discovery — bypassing our privacy defaults) |
| `a.example, b.example` | Value silently becomes a **list** |
| `%(enable_transport)s` | ConfigObj **interpolation** — here a crash; in other cases, reading other settings |
| `peer.example # x` | Trailing text silently treated as a comment |

Building the file with ConfigObj's object API and `write()` neutralised the structural injection
in the same test (each value stayed a single string), but **did not validate content** — the
newline and interpolation markers survived inside the value.

Therefore, defence in depth, for **every** user-controlled field (peer name, host, port, network
name, passphrase, and any future field):

1. **Supervisor schema** (first layer): `match(REGEX)`, `port`, `password`, `list(...)` types in
   `config.yaml`, so the HA UI rejects bad input early.
2. **Core allow-list validation** (authoritative), applied regardless of the schema:
   - *peer name*: `^[A-Za-z0-9][A-Za-z0-9 _.-]{0,31}$` (becomes a ConfigObj section name — no
     brackets, quotes, `#`, `=`, `%`, `$` or control characters), unique, case-insensitive;
   - *host*: a valid DNS hostname (RFC 1123 labels, total ≤ 253, no trailing dot) **or** a valid
     IPv4/IPv6 literal parsed with `ipaddress`; nothing else;
   - *port*: integer 1–65535;
   - *network name*: same rule as peer name;
   - *passphrase*: printable UTF-8, 8–128 characters, and must not contain newline, `#`, `%`, `$`,
     quote characters or a leading/trailing space (the exact set is to be confirmed against
     ConfigObj's quoting rules in Phase 1; **[Open] Q-25**);
   - reject any value containing control characters (including `\r`, `\n`, `\t`, `\0`).
3. **Rendering only through the ConfigObj object API** (never f-strings or templates), with
   RNS-controlled keys taken from a fixed allow-list — user input never becomes a *key*, only a
   section name (validated) or a value (validated).
4. **Round-trip check:** re-parse the rendered file and assert that the parsed structure equals
   the intended structure exactly (same sections, same keys, same scalar values, no extra
   interfaces). Refuse to start otherwise.
5. **Tests:** a fuzz and regression suite of hostile inputs (testing strategy §4).

### 4.2 Process supervision

- RNS runs as a **child process** of the core, as the unprivileged `meshbeacon` user.
- Restart policy: exponential back-off (1 s → 5 min cap); **circuit breaker** after 5 failures in
  15 minutes, retrying after 15 minutes. The app itself stays running and reports the state.
- Graceful shutdown on `SIGTERM` within the Supervisor `timeout` (set to 20 s).

### 4.3 Resource protection

The Supervisor imposes no memory or CPU limits on apps (feasibility §5), so MeshBeacon limits
itself.

| Resource | Control (v0.1) | Notes |
|---|---|---|
| **Memory** | RSS watchdog on the RNS child: controlled restart above a ceiling (default 256 MB; idle ≈ 55 MB measured). Python allocator left to RNS/jemalloc defaults. | `rnstatus -j` also reports `rss` |
| **CPU** | Run RNS and core at reduced priority (`nice 10`) so HA Core always wins contention. Detect sustained high CPU (> 80 % of one core for > 10 min) and log a warning; do not kill (stamp generation legitimately spikes CPU). | No cgroup control without privileges |
| **Storage** | Check free space on `/data` before start and hourly; refuse to start below 200 MB free, warn below 1 GB. Cap regenerable RNS directories (`cache/`, `resources/`) — clear them on start if above a size cap (default 100 MB). SQLite stays on `/data` (SSD), never tmpfs. | **[Assumption]** RNS cleans its cache periodically (Transport `clean_cache`, every 5 min) — verify bound in soak test |
| **Logs** | RNS stdout/stderr is read by the core and forwarded to the app log with **rate limiting** (default ≤ 20 lines/s with a burst allowance; excess summarised as "N lines suppressed"). RNS log level ≤ 4 by default. RNS file logging is not used (it would rotate at 5 MB, verified `RNS/__init__.py` `LOG_MAXSIZE`, but duplicates journald). | HA OS journald provides persistence |
| **Network** | Transport off by default. RNS's native announce cap (2 % of interface bandwidth by default) and ingress control stay at upstream defaults. Byte counters from RNS logged in the periodic status line; optional monthly data warning. | No quota *enforcement* in v0.1 — warning only (**[Open] Q-26**) |
| **File descriptors** | `ulimits: nofile` set to a modest value (proposed 4096) in `config.yaml` | |
| **Threads / processes** | One RNS child; no unbounded worker pools in the core | |

### 4.4 Health model: process health versus network connectivity

Two independent dimensions, never conflated:

| Dimension | States | Drives |
|---|---|---|
| **Process health** | `starting` · `running` · `restarting` · `failed` (circuit breaker open) | Health endpoint → Supervisor watchdog |
| **Network connectivity** | `isolated` (no peers configured) · `offline` (peers configured, none up) · `partial` (some up) · `online` (all up) | Status messages (v0.1); entities (v0.2) |

The **health endpoint returns success whenever the core is running and the RNS child is running
or is being restarted within its back-off policy.** It does *not* fail when the internet is down,
when peers are unreachable, or when the node is isolated — otherwise an internet outage would make
the Supervisor restart the app repeatedly, which cannot help and wears the SSD.

### 4.5 Supervisor watchdog

**[Verified]** (Supervisor `e610ca8`, `supervisor/misc/tasks.py` `_watchdog_app_application`,
`supervisor/apps/app.py` `watchdog_application`):

- The app's `watchdog` URL is checked **every 120 s**; on the **second consecutive failure** the
  Supervisor **restarts the whole app**.
- HTTP checks go to the **container's IP on the internal port** (`{ip_address}:{port}`), so **no
  port needs publishing** and **no API permission is needed**. A `tcp://` check is also supported.
- Separately, if the watchdog is enabled, a container state of `failed`, `stopped` or `unhealthy`
  triggers a restart, with throttling (`WATCHDOG_THROTTLE_MAX_CALLS = 10` per 30 minutes).
- The watchdog is a **per-user toggle that defaults to off** (`ATTR_WATCHDOG` default `False`).

**[Recommendation]**

- Declare `watchdog: "http://[HOST]:[PORT:8099]/health"` (port to be fixed in Phase 1), served by
  the core on the container's internal interface only; responds `200` with a minimal body (no
  identities, no peer details) and never needs authentication because it reveals nothing.
- The core's own supervisor handles RNS restarts; the Supervisor watchdog is the **last resort**
  for a hung core. Recommend users enable it in `DOCS.md`.

### 4.6 Identity: crash-safe initialisation and restoration

**[Verified]** facts driving this design:

- RNS writes the identity with a plain `open(path, "wb")` + `write()` — no temporary file, no
  `fsync`, no atomic rename (`RNS/Identity.py` `to_file`).
- **RNS silently replaces a corrupt identity.** A 10-byte `transport_identity` produced
  "Failed to load identity key" followed by "No valid Transport Identity in storage, creating…",
  and the file was **overwritten** with a new 64-byte key (test, RNS 1.6.0).
- RNS creates the file 0644 under the default umask.

Design:

1. **MeshBeacon owns identity creation.** On first start, the init step generates the identity
   *before* RNS starts: generate with RNS's public `RNS.Identity()` API, write to a temporary
   file in the same directory (0600), `fsync` the file, `rename` it into place, `fsync` the
   directory. RNS then only ever *loads* it.
2. **Validate before every start.** The init step loads the file with `RNS.Identity.from_file()`
   in a separate short-lived process and checks it is exactly 64 bytes and loads successfully. On
   failure, **RNS is not started**, so it cannot overwrite the file.
3. **Keep a verified second copy** (`/data/meshbeacon/identity.backup`, 0600), written atomically
   after first successful validation, and compare hashes at each start. If the primary is damaged
   and the backup is valid, restore from the backup automatically and log it. If both are damaged,
   stop with the identity-problem message ([first-run UX §5](ux/first-run.md#5-plain-language-status-messages)).
4. **Record the identity hash** (not the key) in `/data/meshbeacon/state.json` so MeshBeacon can
   detect any unexpected change between starts and refuse to continue.
5. **Explicit regeneration only** via an advanced option *"Replace identity on next start"*,
   which resets itself after use and logs the old and new hashes.
6. **Restoration**:
   - *From a Home Assistant backup:* the normal path. `/data` (including the identity and its
     backup copy) is restored by the Supervisor; validation (2) runs on next start.
   - *Import from a file* (migration from another Reticulum install): deferred to v0.2, because it
     needs a file-transfer path into `/data` (for example `app_config` mapping) that adds
     permissions. Requirements recorded now: 64-byte raw format, validated with the RNS API, show
     the resulting identity hash in the log for the user to confirm, atomic write, and the
     imported file deleted from the shared location afterwards.
7. **Backups:** `backup: hot`; `backup_exclude` for `reticulum/storage/cache/**` and
   `reticulum/storage/resources/**`; `backup_pre` checkpoints SQLite. Whether a hot backup of the
   RNS SQLite database is consistent remains feasibility Q-7; `backup: cold` is the safe fallback.

### 4.7 Privilege model inside the container

**[Verified]** HA base images use **s6-overlay v3**, which runs as root as PID 1 (`docker-base`
`7d9ba08`). Docker's default capability set (which the Supervisor uses, minus `NET_RAW` and others
in its planned reduced profile) includes `CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE` and `FOWNER`.

Design:

- A dedicated system user and group **`meshbeacon`** (fixed UID/GID, no login shell, no home
  directory beyond `/data/meshbeacon`) is created in the image.
- A root **init step** (s6 `cont-init`/oneshot) does only: read `/data/options.json`, validate
  it, set `umask 077`, create `/data/meshbeacon` and `/data/reticulum`, `chown` them to
  `meshbeacon`, repair modes (0700 dirs, 0600 files), validate the identity, and render the RNS
  config. It writes nothing else.
- The **core and the RNS child run as `meshbeacon`** via `s6-setuidgid`. They cannot write to
  the image filesystem.
- No `privileged` capabilities are requested. **[Assumption]** RNS TCP client interfaces need
  no capabilities (no raw sockets, no privileged ports) — confirm in Phase 1 by running with all
  capabilities dropped.
- AppArmor: a custom profile restricting the core and RNS to `/data/**` (read/write), the Python
  installation (read-only), and TCP/UDP network access; denying everything else.
- "Where supported": if a future feature needs root (none in v0.1), it must be isolated in its own
  s6 service, documented and justified in an ADR.

### 4.8 Storage layout (under `/data`)

```text
/data/                      root-owned mount, always present
  options.json              written by the Supervisor (read by init only)
  meshbeacon/               0700 meshbeacon
    state.json              0600 non-secret runtime state, identity hash
    identity.backup         0600 verified copy of the transport identity
  reticulum/                0700 meshbeacon   (RNS --config directory)
    config                  0600 rendered on every start (contains rpc_key)
    storage/
      transport_identity    0600 created atomically by MeshBeacon
      known_destinations.db (+ -wal, -shm)
      cache/ resources/     regenerable, size-capped, excluded from backups
      blackhole/ identities/
```

## 5. Networking posture

- `host_network: false`; outbound TCP only. This keeps RNS's abstract Unix sockets inside the
  container's own network namespace (feasibility §10, item 3).
- No published ports. No TCP listener in v0.1.
- Never rendered in v0.1: `AutoInterface`, `discover_interfaces`, `discoverable`,
  `autoconnect_discovered_interfaces`, `publish_ifac`, `location_cmd`, I2P, RNode.
- No default peer. Optional verified presets only ([ADR 0004](adr/0004-public-peer-presets.md)).
- Explicit random `rpc_key` (validated hex — RNS silently falls back to the identity-derived key on
  an invalid value) and a unique `instance_name`.

## 6. Dependency and build policy

- Python dependencies pinned **by version and hash**, installed with `--require-hashes`.
- Base image pinned **by digest**.
- Multi-arch images (`aarch64`, `amd64`) built with `home-assistant/builder` actions,
  **Cosign-signed**, with SBOM attestations.
- **No image is published** until the licensing obligations O1–O7 are implemented
  ([licensing §5](research/licensing.md#5-obligations-before-publishing-images)).

## 7. Evolution by version

| Version | Architectural additions |
|---|---|
| **v0.1** | Init step, core supervisor, config renderer, identity manager, health endpoint, status reporter, resource guards, app wrapper. **Nothing else.** |
| v0.2 | Token-authenticated local API (internal network only); HA integration (entities, repairs, diagnostics); identity import; Supervisor discovery (permission review needed — Q-11) |
| v0.3 | LXMF service, notify platform, optional propagation node |
| v0.4 | Optional I2P (separate router process); public-gateway investigation |
| v0.5 | RNode via explicit device mapping |
| v0.6 | Authenticated remote commands with allowlists and replay protection |
| v1.0 | Standalone Docker packaging |

## 8. Deliberately excluded

No custom cryptography or protocol code; no cloud services, telemetry or analytics; no Docker
socket, privileged mode or `manager`/`admin` Supervisor role; no write access to the Home
Assistant configuration directory; no raw RNS configuration pass-through.
