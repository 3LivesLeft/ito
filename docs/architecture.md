# Architecture

Status: **Proposed — revised after independent review** · No application code exists yet. This
describes the intended structure so that Phase 1 can be reviewed against it.

Evidence and reasoning: [feasibility study](research/feasibility.md),
[ADR 0001](adr/0001-networking-foundation.md), [threat model](security/threat-model.md),
[first-run UX](ux/first-run.md).

## 1. Goals that shape the architecture

1. **Easy to use.** Safe defaults; a handful of plainly named options; status messages written for
   people ([first-run UX](ux/first-run.md)).
2. **Reuse upstream.** RNS (and later LXMF) do all protocol work. ito configures,
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
│  ┌──────────────── ito app container (bridged network) ──────────────┐  │
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
   - *passphrase*: printable **ASCII**, 1–128 characters, excluding `"`, `'`, `#`, `,`, `%`, `$`
     and `\`, with no leading or trailing space (**Q-25 resolved in Phase 1**: with this set,
     ConfigObj round-trips every value exactly — verified by property-based tests; 1 rather than 8
     characters minimum so that users can join existing networks whose passphrases they do not
     control);
   - reject any value containing control characters (including `\r`, `\n`, `\t`, `\0`).
3. **Rendering only through the ConfigObj object API** (never f-strings or templates), with
   RNS-controlled keys taken from a fixed allow-list — user input never becomes a *key*, only a
   section name (validated) or a value (validated).
4. **Round-trip check:** re-parse the rendered file and assert that the parsed structure equals
   the intended structure exactly (same sections, same keys, same scalar values, no extra
   interfaces). Refuse to start otherwise.
5. **Tests:** a fuzz and regression suite of hostile inputs (testing strategy §4).

### 4.2 Process supervision and bounded recovery

See §4.5 for how this interacts with the Supervisor watchdog. In short: **every restart path is
bounded, and no condition that a restart cannot fix is ever reported as unhealthy.**

**Failure classes.** Before starting RNS, the core classifies problems:

| Class | Examples | Action |
|---|---|---|
| **Deterministic** (a restart cannot fix it) | Invalid options; identity invalid and no valid backup; identity fingerprint mismatch; "replace identity" left switched on; `/data` below the free-space floor; RNS refuses the rendered config | **Do not start RNS.** Enter `needs_attention` immediately, with a plain-language message. No retries until the options change or the app is restarted by the user. |
| **Transient** (may recover) | RNS child exits or crashes; memory guard restart | Restart the RNS child with exponential back-off (1 s → 5 min cap). |

**Internal circuit breaker (transient failures).**

1. After **5 child failures within 15 minutes**, the breaker opens and the core waits 15 minutes
   before one more attempt (half-open).
2. If the breaker opens **3 times without the child staying up for at least 10 minutes in
   between**, the core stops retrying and enters `needs_attention` ("The Reticulum service keeps
   failing; ito has stopped trying. Restart the app after fixing the cause.").
3. A child that stays up for 10 minutes resets all counters.

Worst case before giving up: about an hour, then nothing further until the user acts.

**Persistent start history (whole-app restarts).** Each core start appends a timestamp to
`state.json`. If the app has started **5 times within 30 minutes without once reaching 10 minutes
of stable running**, whatever caused those restarts (the Supervisor watchdog, a crash of the core
itself, the host), the core starts in **safe mode**: it does not start RNS, reports
`needs_attention`, and explains that it has paused after repeated restarts. Because the core stays healthy in safe
mode, nothing restarts it, so the 30-minute window expires naturally. Safe mode is left when the
options change (detected by a hash of the validated settings), or on the first start after the
window has expired; the message tells the user the time after which a restart will try again.

**Core process exit.** If the core itself exits, s6-overlay's `finish` script stops the container
with a non-zero code rather than restarting the core indefinitely inside the container. Whether the
container is then restarted is the Supervisor's decision (§4.5), and the start history above bounds
it.

**Shutdown.** `SIGTERM` is honoured within the Supervisor `timeout` (set to 20 s).

### 4.3 Resource protection

The Supervisor imposes no memory or CPU limits on apps (feasibility §5), so ito limits
itself.

| Resource | Control (v0.1) | Notes |
|---|---|---|
| **Memory** | Memory watchdog on the RNS child counting **RSS + swap** (`VmRSS` + `VmSwap`), so swapping on a device with swap cannot hide growth: controlled restart above a ceiling (default 256 MB; idle ≈ 55 MB measured). The core itself stays small: standard library only where practical, no web framework in v0.1, no in-memory history beyond a bounded status window. Python allocator left to RNS/jemalloc defaults. | `rnstatus -j` also reports `rss`. Defaults target low-memory devices, not the 8 GB reference board |
| **CPU** | Run RNS and core at reduced priority (`nice 10`) so HA Core always wins contention. Detect sustained high CPU (> 80 % of one core for > 10 min) and log a warning; do not kill (stamp generation legitimately spikes CPU). | No cgroup control without privileges |
| **Storage** | Check free space on `/data` before start and hourly; refuse to start below 200 MB free, warn below 1 GB. Cap regenerable RNS directories (`cache/`, `resources/`) — clear them on start if above a size cap (default 100 MB). SQLite stays on `/data` (SSD), never tmpfs. | **[Assumption]** RNS cleans its cache periodically (Transport `clean_cache`, every 5 min) — verify bound in soak test |
| **Logs** | RNS stdout/stderr is read by the core, **redacted** (every `<32 hex>` destination/identity hash and every hex or base64 blob of key length is replaced with `<redacted>` — RNS prints identity hashes at log level 5, verified), then forwarded to the app log with **rate limiting** (default ≤ 20 lines/s with a burst allowance; excess summarised as "N lines suppressed"). RNS log level ≤ 4 by default. RNS file logging is not used (it would rotate at 5 MB, verified `RNS/__init__.py` `LOG_MAXSIZE`, but duplicates journald). | HA OS journald provides persistence |
| **Network** | Transport off by default. RNS's native announce cap (2 % of interface bandwidth by default) and ingress control stay at upstream defaults. Byte counters from RNS logged in the periodic status line; optional monthly data warning. | No quota *enforcement* in v0.1 — warning only (**[Open] Q-26**) |
| **File descriptors** | `ulimits: nofile` set to a modest value (proposed 4096) in `config.yaml` | |
| **Threads / processes** | One RNS child; no unbounded worker pools in the core | |

### 4.4 Health model: process health versus network connectivity

Two independent dimensions, never conflated:

| Dimension | States | Drives |
|---|---|---|
| **Process health** | `starting` · `running` · `restarting` · `needs_attention` · `unresponsive` | Health endpoint → Supervisor watchdog |
| **Network connectivity** | `isolated` (no peers configured) · `offline` (peers configured, none up) · `partial` (some up) · `online` (all up) | Status messages (v0.1); entities (v0.2) |

**The health endpoint answers `200 OK` whenever the core's event loop is responsive** — in
`starting`, `running`, `restarting` *and* `needs_attention`. It fails only when the core is
`unresponsive` (the endpoint cannot be served, or the core's internal heartbeat is older than
60 s). Rationale:

- An internet outage, unreachable peers or an isolated node are connectivity states; a restart
  cannot help, and restarts would wear the SSD.
- `needs_attention` covers failures a restart cannot fix; reporting them as unhealthy would make
  the Supervisor restart the app forever (§4.5).
- A hung core *can* be fixed by a restart, which is exactly what the Supervisor watchdog is for.

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

**[Verified]** Neither Supervisor watchdog path stops by itself: application-check restarts
are not throttled, and container-state restarts are rate-limited to 10 per 30 minutes
(`JobThrottle.GROUP_RATE_LIMIT`), which bounds their *rate*, not their number
(`_restart_after_problem`, Supervisor 2026.11.0). ito must therefore make sure a loop
cannot arise.

**Design — how the two mechanisms fit together:**

| Situation | Internal mechanism | Health endpoint | Supervisor watchdog | Can it loop? |
|---|---|---|---|---|
| Internet down / peers unreachable / isolated | None (connectivity state only) | 200 | No action | No |
| RNS child crashes occasionally | Back-off restarts of the child | 200 | No action | No |
| RNS child crash-loops | Breaker opens ≤ 3 times, then `needs_attention` | 200 | No action | No — stops after ~1 h |
| Deterministic problem (bad identity, bad config, low disk) | `needs_attention` immediately, RNS not started | 200 | No action | No |
| Core hangs | — | Fails | Restarts the app after 2 failed checks (~4 min) | Bounded by start history → safe mode after 5 starts in 30 min |
| Core process exits | s6 stops the container | n/a | Container `failed` → restart (if enabled), ≤ 10 per 30 min | Bounded by start history → safe mode |
| Host reboot | Normal start | 200 | — | Start history counts it; a 10-minute stable run resets the count |

**Settings:**

- Declare `watchdog: "http://[HOST]:[PORT:8099]/health"` (port fixed in Phase 1), served on the
  container's internal interface only; the response body is minimal (`ok`) and reveals no
  identities, peers or state details, so no authentication is needed.
- `DOCS.md` recommends enabling the watchdog; ito is safe with it on or off.
- No Supervisor API permission is needed for any of this.

### 4.6 Identity: crash-safe initialisation and restoration

**[Verified]** facts driving this design:

- RNS writes the identity with a plain `open(path, "wb")` + `write()` — no temporary file, no
  `fsync`, no atomic rename (`RNS/Identity.py` `to_file`).
- **RNS silently replaces a corrupt identity.** A 10-byte `transport_identity` produced
  "Failed to load identity key" followed by "No valid Transport Identity in storage, creating…",
  and the file was **overwritten** with a new 64-byte key (test, RNS 1.6.0).
- RNS creates the file 0644 under the default umask.

Design:

1. **ito owns identity creation.** On first start, the init step generates the identity
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
4. **Record a fingerprint** of the identity (its public hash, never the key) in
   `/data/meshbeacon/state.json` (0600) so ito can detect any unexpected change between
   starts and refuse to continue. The fingerprint is **never written to logs**; the log says only
   "Node identity: unchanged since last start" or explains a change in words.
5. **Explicit regeneration only** via an advanced option *"Replace identity on next start"*.
   When used, the old identity is kept as `identity.replaced-<UTC timestamp>` (0600) for manual
   recovery, the log says "Node identity replaced as requested; the previous identity has been
   kept in the app's data folder" — **without any hashes** — and the option must be switched off
   again by the user before the next restart, otherwise ito refuses to start and explains
   why (it cannot switch the option off itself without Supervisor API access).
   **Replacement is a journalled transaction** (PR #2 review): (1) the new key is staged as
   `identity.pending`; (2) the state file records the replacement as authorised — the commit
   point; (3) the current identity is kept, the new one is written as primary and backup, and the
   state is committed. A crash before (2) leaves the original in use; after (2), the next start
   finishes *that* replacement whatever the option says, so it is applied exactly once and the
   identity never changes silently. Verified by injecting a crash before each of the six writes.
6. **Restoration**:
   - *From a Home Assistant backup:* the normal path. `/data` (including the identity and its
     backup copy) is restored by the Supervisor; validation (2) runs on next start.
   - *Import from a file* (migration from another Reticulum install): deferred to v0.2, because it
     needs a file-transfer path into `/data` (for example `app_config` mapping) that adds
     permissions. Requirements recorded now: 64-byte raw format, validated with the RNS API,
     confirmation shown to the user in the v0.2 integration UI (never in logs), atomic write, and
     the imported file deleted from the shared location afterwards.
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
- AppArmor: a custom profile (revised after the v0.1.0 start-up failure on the reference Pi).
  Read access to the container's own filesystem; execution only from the image's program
  directories and s6-overlay's run-time service directories (never from `/data` or `/tmp`); writes
  only to `/data`, `/tmp`, s6-overlay's own folders in `/run` and the discovery relay's folder
  (owner-only rule; narrowed in M1.2); a short capability list (none added since v0.1); mount,
  pivot_root and ptrace denied. One profile covers every process: AppArmor selects a profile by
  executable path, and the core and Reticulum both run `python3`, so a separate Reticulum profile
  would need a second interpreter path. That, and running Reticulum as another user, is deferred
  to an ADR before any write-capable credential exists. s6-overlay starts with shell scripts (`/init` is `#!/bin/sh -e`), and an interpreter must
  be able to read a script it runs — the 0.1.0 profile allowed only execution, so `/bin/sh` could
  not open `/init`. **The Supervisor loads the profile only on install and on update to a new
  version, not on Rebuild** (Supervisor 2026.11.0, `apps/app.py`), and renames it to the app slug.
- "Where supported": if a future feature needs root (none in v0.1), it must be isolated in its own
  s6 service, documented and justified in an ADR.
- **v0.3 (M1): the discovery relay** is the first such root service
  (`services.d/discovery-relay`, `core/meshbeacon/discovery_relay.py`;
  [ADR 0006 amendment](adr/0006-local-metrics-api.md#amendment-19-november-2026-m1-how-discovery-reaches-the-supervisor)).
  Newer Supervisors give the app a root-only (0600) socket. The relay's own socket is root-only
  too; the core's run script runs a short root start step (`relay_link.py`) that opens the link
  and hands it to the core. On the compatibility path the same step passes the Supervisor token
  through a one-time pipe instead, so it is in no process environment. The core makes itself
  non-dumpable before it reads either, so Reticulum, though it runs as the same user, cannot reach
  the core's memory, environment or descriptors (threat T72; M1.2). The relay sends only
  ito's validated discovery message and does not run where there is no socket.
- **Process isolation (ADR 0018, M4 WP1):** the core runs as `meshbeacon` (9100); Reticulum and its
  prepare step run as `mb-rns` (9101) as s6 services that start down, which the core controls
  (`s6-svc`, permissions granted by `s6-svperms`) and reads through FIFOs in `/run/meshbeacon-io/`.
  `/data/meshbeacon` belongs to the core and `/data/reticulum` (identity, backup, configuration) to
  Reticulum; `/data` is 0711 and `options.json` is readable by the `mb-options` group only. Separate
  users for LXMF and each community service are mandatory before M4 is accepted or any community
  service is introduced ([roadmap](roadmap.md#process-isolation-gate-mandatory)).

### 4.8 Storage layout (under `/data`)

```text
/data/                      root-owned mount, always present
  options.json              written by the Supervisor (read by init only)
  meshbeacon/               0700 meshbeacon
    state.json              0600 runtime state: identity fingerprint, start history
    identity.backup         0600 verified copy of the transport identity
  reticulum/                0700 meshbeacon   (RNS --config directory)
    config                  0600 rendered on every start (contains rpc_key)
    storage/
      transport_identity    0600 created atomically by ito
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
- **`share_instance = No`** (Phase 1): RNS opens **no local sockets and no RPC listener at all**
  (verified: no Unix or TCP sockets in the RNS process with default options). A fresh random
  `rpc_key` is still rendered on every start, for defence in depth.
- Explicit random `rpc_key` (validated hex — RNS silently falls back to the identity-derived key on
  an invalid value) and a unique `instance_name`.

## 6. Dependency and build policy

- Python dependencies pinned **by version and hash**, installed with `--require-hashes`.
- Base image pinned **by digest**.
- Multi-arch images (`aarch64`, `amd64`) built with `home-assistant/builder` actions,
  **Cosign-signed**, with SBOM attestations.
- **No image is published** until the licensing obligations O1–O7 are implemented
  ([licensing §5](research/licensing.md#5-obligations-before-publishing-images)).

## 6a. Interface layers (v0.2; maintainer requirement, 18 Nov 2026)

The core, the secure API, the presentation and the delivery mechanism are maintained
independently. Each layer depends only on the one below through a versioned contract, so a new
delivery (the built-in interface, once a secure one exists) or a new feature (LXMF messaging,
I2P, LoRa) adds a part without reworking the others.

```text
 delivery     meshbeacon-panel.js (integration panel, today) | ingress.js (bundled app dashboard, ADR 0026)
                     │ chooses a source, supplies chrome (menu button, routing) and wording
 presentation ui/controller.js · ui/views.js · ui/components.js · ui/style.js · ui/dom.js · tokens.js
                     │ reads only the view-data contract (model.js NODE_KEYS / PEER_KEYS / HISTORY_KEYS)
 data sources sources/hass.js (HA entities + recorder) | sources/snapshot.js (core snapshot + history provider)
                     │
 secure API   GET /api/v1/status, schema 1, pinned TLS (ADR 0006) → integration entities
                     │
 core         metrics.py (the only metrics implementation), supervisor, RNS child
```

| Layer | Contract | Rules (enforced by tests) |
|---|---|---|
| Core | Status snapshot, schema 1 | Metrics computed only in `metrics.py` |
| Secure API | `GET /api/v1/status` | Pinned TLS, token, read-only (ADR 0006); messaging adds its own scoped API (ADR 0010, proposed) |
| Data sources | `reading(key)`, `has`, `peers`, `peerState`, `availability`, `version`, `history` | No DOM (`tests/frontend/sources.test.mjs`); both sources return complete readings for every key |
| Presentation | Components and views take plain values or a source | No Home Assistant objects, network or storage (`sources.test.mjs`); only design tokens (`tokens.test.mjs`); `textContent` only |
| Delivery | Wires a source, the controller and host chrome | The only place that knows its host (Home Assistant today) |

`tools/panel_preview.html?source=snapshot` renders the same views from a schema-1 snapshot
through `sources/snapshot.js`, with no Home Assistant. It shows that the presentation does not
depend on the delivery. The built-in interface's remaining needs are a secure delivery and the
seven-day memory-only history (decision D3), not new presentation code.

## 6b. Distribution and node identity in Home Assistant (v0.3, M1)

[ADR 0015](adr/0015-distribution-and-updates.md):

- One repository serves two installers: the Supervisor **app store** reads `repository.yaml` and
  `meshbeacon/config.yaml`; Home Assistant's **Marketplace** reads `hacs.json` and
  `custom_components/meshbeacon/`. One version and one tag cover both
  ([releasing](releasing.md)); `tools/check_release.py` checks the layout.
- Identifiers live in `project.yaml`; `tests/unit/test_project_identifiers.py` checks every copy.
- The integration's config entry (version 2) separates **`node_key`** (the stable prefix of entity
  unique IDs) from **`app_slug`** (the app it talks to now), so the app can move between slugs
  without changing entity IDs or history. Config entries hold only allow-listed keys.
- The integration and the app may update at different times; `compatibility.py` raises a repair
  that names the part to update.

## 6c. Node services independent of Home Assistant

[ADR 0017](adr/0017-independent-node-services.md): the core and its services (messaging from v0.3;
later pages, boards, libraries, voice) run without Home Assistant; Home Assistant is a first-class
management interface, through bindings of a versioned management contract, never a runtime
dependency.

## 7. Evolution by version

| Version | Architectural additions |
|---|---|
| **v0.1** | Init step, core supervisor, config renderer, identity manager, health endpoint, status reporter, resource guards, app wrapper. **Nothing else.** |
| v0.2 | **In progress** ([v0.2 design](research/v0.2-observability.md), [ADR 0006](adr/0006-local-metrics-api.md)): opt-in, read-only, token-authenticated status API on internal port 8100; Supervisor discovery (verified: needs no `hassio_api`, Q-11); HA integration (entities, repairs, diagnostics); metrics computed only in `core/meshbeacon/metrics.py`; a sidebar panel served by the integration ([ADR 0007](adr/0007-sidebar-panel.md)): one plain JS module, live values from HA entities, history from HA's recorder, admin-only, no app-side change. Identity import deferred |
| v0.3 | LXMF service, notify platform, optional propagation node. Decisions that could constrain later milestones: [forward-compatibility review](research/long-term-direction.md) |
| v0.4–v0.8+ | *Proposed* ([roadmap](roadmap.md#long-term-direction-proposed)): page hosting, community services, voice bursts, replication. Not designed |
| Unscheduled | Optional I2P (separate router process); RNode via explicit device mapping; authenticated remote commands with allowlists and replay protection ([previously planned items](roadmap.md#previously-planned-items)) |
| v1.0 | Standalone Docker packaging |

## 8. Deliberately excluded

No custom cryptography or protocol code; no cloud services, telemetry or analytics; no Docker
socket, privileged mode or `manager`/`admin` Supervisor role; no write access to the Home
Assistant configuration directory; no raw RNS configuration pass-through.

## 9. Phase 1 implementation notes (v0.1.0)

How the design above was implemented, and decisions taken during implementation.

| Topic | Implementation | Where |
|---|---|---|
| Package layout | App folder `meshbeacon/` (Supervisor build context) containing `core/meshbeacon/` (the HA-free core), `rootfs/` (s6 scripts), `config.yaml`, `Dockerfile`, `apparmor.txt` | repository root |
| Processes | s6-overlay PID 1 → root `cont-init` (folders and ownership only, never fails) → `meshbeacon.supervisor` as user `meshbeacon` (UID 9100) → per start: short-lived `meshbeacon.prepare`, then long-running `meshbeacon.node` | `rootfs/`, `core/meshbeacon/` |
| RNS child (Q-12 resolved) | A thin entry point, `meshbeacon.node`, that calls `RNS.Reticulum(configdir=…)` and reports `get_interface_stats()` (names, up/down, byte counters only) as JSON lines over a dedicated pipe every 10 s | `node.py` |
| RNS import | Only `prepare` and `node` import RNS; the long-running supervisor does not (≈ 25 MB instead of ≈ 45 MB) | |
| Config parser | Rendering and round-trip verification use the ConfigObj copy that RNS ships (`RNS.vendor.configobj`), so verification uses exactly the parser RNS will use; no private attributes are touched | `rnsconfig.py` |
| Identity | Created with `RNS.Identity()` / `get_private_key()`, validated with `RNS.Identity.from_bytes()` (public API). **Finding:** any 64 bytes form a valid key pair, so same-length corruption looks like a different identity; ito therefore restores from the verified backup whenever the backup matches the recorded fingerprint | `identity.py` |
| Orphan prevention | The RNS child asks the kernel for `SIGTERM` when the supervisor dies (`PR_SET_PDEATHSIG`); the s6 `finish` script stops the container on any crash of the core (including `SIGKILL`) instead of restarting it inside the container. Found by container test: without this, a killed core left RNS running and a second RNS started on the same storage | `procinfo.py`, `finish` |
| Child Python | `python3 -I -u` when installed in site-packages, as in the image. `-u` is required: RNS logs with `print()`, and `-I` ignores `PYTHONUNBUFFERED`, so without it RNS output reached the log late or not at all (found by the network-isolated test run) | `supervisor.py` |
| Timings | Back-off 1 s → 5 min; breaker 5 failures / 15 min, 15 min cool-down, give up after 3 openings; stable after 10 min; status every 10 s, stall after 120 s; start history 5 starts / 30 min | `policy.py` |
| Logging | Every line redacted (32-hex hashes, longer hex runs, mixed-case base64 runs ≥ 43 characters, configured passphrases), truncated to 1,000 characters, and RNS output rate-limited to 20 lines/s with a burst of 100 | `logfilter.py` |
| Resource guards | `nice 10`; memory guard on RSS + swap; CPU warning after 10 min above 80 % of a core; free-space floor 200 MB (warning below 1 GB); regenerable RNS cache cleared above 100 MB at start; `ulimits: nofile 4096` | `supervisor.py`, `prepare.py`, `config.yaml` |
| Health endpoint | `GET /health` on port 8099, `200 ok` while the main loop heartbeat is < 60 s old, `503` otherwise; request logging disabled. The heartbeat is kept fresh while waiting for bounded subprocesses (the prepare step, up to 180 s, and the stop grace period), so a slow start cannot cause a Supervisor restart (PR #2 review) | `health.py`, `supervisor.py` |
| Build | Base image pinned by multi-arch digest; runtime wheels hash-pinned and binary-only from PyPI; optional BuildKit secret `build_ca` for builds behind TLS-intercepting proxies (never stored in the image) | `Dockerfile` |
| AppArmor | Rewritten after the start-up failure on the Pi. Tested statically (every program the profile lets run must also be readable if it is a script) and **under real enforcement in CI** on an AppArmor-enabled runner; still to be confirmed on the Pi | `apparmor.txt`, `tests/apparmor/`, CI |

## Nomad Network pages (0.6.0)

See [ADR 0027](adr/0027-nomad-network-pages.md). One more optional service, off by default:

```text
 core (meshbeacon)            pages content store (/data/pages), /api/pages, supervision
   │  JSON lines over /run/meshbeacon-pages/pages.sock (peer-checked, group mb-page)
   ▼
 pages service (mb-nomad)     python -m meshbeacon.pages: RNS shared-instance client
   ├─ browse                  Link + request for /page/*.mu, plain text back to the core
   ├─ discover                announce handler for nomadnetwork.node (500 nodes, nodes.json)
   └─ host (while on)         child: unmodified `nomadnet --daemon`, pages_path = /data/pages/public
```

Storage: `/data/pages/` (core, group `mb-page`: `site.json`, `drafts/` 0700, `public/` 0750 with
0640 files) and `/data/nomadnet/` (`mb-nomad` 0700: `rns/` client configuration, `nomadnet/`
daemon configuration and storage including its identity, `nodes.json`, `files/`).

## Bundled app dashboard (0.5.0)

See [ADR 0026](adr/0026-app-dashboard-and-setup.md) for the accepted Ingress trust boundary,
self-only configuration API, content-versioned frontend, optional integration and upgrade behaviour.
