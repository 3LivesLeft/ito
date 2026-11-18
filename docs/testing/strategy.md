# Testing strategy

Status: **Proposed (Phase 0)**. Nothing here is implemented yet.

## 1. Principles

- **Never touch a live network or a live Home Assistant in automated tests.** Every Reticulum
  node in a test is isolated (feasibility §11). No test may connect to a public Reticulum entry
  point.
- **Test against the real reference implementation**, at the pinned version, not mocks of it —
  except in unit tests of MeshBeacon's own logic.
- **Every RNS upgrade runs the full integration suite** before the pin is changed (risk R-1, R-5).
- Tests are part of the definition of done for every change.

## 2. Test layers

| Layer | Scope | Tooling (proposed) | Runs |
|---|---|---|---|
| Static | Lint, format, type check, shellcheck, hadolint, YAML schema of `config.yaml` | ruff, mypy, shellcheck, hadolint | Every push |
| Unit | Settings validation, config rendering (golden files), back-off logic, health state machine, permission repair, log redaction | pytest | Every push |
| Integration — isolated RNS | Real `rnsd` processes in temp config dirs, loopback/bridge TCP | pytest + subprocess fixtures | Every push |
| Container | Build image for amd64 and aarch64 (QEMU); start it with a fake `/data/options.json`; assert health, permissions, no listening host ports | Docker Buildx, pytest | Every PR |
| HA integration (v0.2+) | Custom component against HA's test harness | `pytest-homeassistant-custom-component` | Every PR |
| Supervisor end-to-end | App installed in HA devcontainer (Supervisor + Core) | `home-assistant/devcontainer` | Before release |
| Reference environment | Raspberry Pi 4B, HA OS 18.5, co-installed apps, real network: compatibility, soak, outage, power and backup tests (§6) | Manual, maintainer-run | Before release |
| Interop | Against Sideband, NomadNet, MeshChat, Ratspeak (v0.3+) | Manual checklist, scripted where possible | Before release |

## 3. Isolated Reticulum test networks

**Verified in Phase 0** with RNS 1.6.0: two `rnsd` instances with separate `--config` directories,
unique `instance_name`s, a `TCPServerInterface` on `127.0.0.1` and a `TCPClientInterface`
connecting to it, connected and reported status through `rnstatus --config <dir> -j`.

Rules for fixtures:

1. Each node: own temporary config directory, unique `instance_name` (isolates the abstract Unix
   sockets), unique ports, `AutoInterface` absent, no external remotes, `loglevel` ≥ 5 captured to
   file for debugging.
2. One process per node (RNS is a per-process singleton).
3. Wait on readiness by polling RPC/`rnstatus -j`, not by sleeping.
4. Tear down by `SIGTERM` and assert clean exit; kill after timeout.
5. Run tests in a network namespace or container with **no default route** in CI where possible,
   so an accidental external connection fails rather than leaks.

Topologies to cover:

| Topology | Purpose |
|---|---|
| A ↔ B (client/server) | Basic connectivity, stats, reconnection |
| A → T → B (T has transport) | Transport mode, path discovery, announce propagation |
| A ↔ B with IFAC (`network_name`/`passphrase`) | Interface access control; mismatched passphrase must fail |
| Server killed and restarted | Client reconnection, `degraded` → `healthy` transitions |
| Flood generator → T | Resource bounds with filters enabled (bounded, local only) |
| LXMF A → B, A → propagation node → B (v0.3) | Messaging, offline delivery |
| Mixed RNS versions (pinned and next) | Upgrade compatibility, stamp enforcement (1.6.2) |

## 4. Security tests (mandatory)

### 4.1 Files, secrets and privileges

- Identity, config and state files are `0600`; directories `0700`, owned by `meshbeacon` — after
  first start, after restart and after RNS has run.
- The core and RNS processes run as the `meshbeacon` user (assert UID/GID from `/proc`); the image
  works with **all** capabilities dropped (`--cap-drop ALL`) apart from those the root init step
  needs (`CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE`, `FOWNER` — to be minimised in Phase 1).
- No private key bytes (hex or base64 of the 64-byte identity), RPC key, passphrase, token **or
  identity/destination hash** appears in any log at any offered log level — including during
  first start, backup restoration and explicit identity replacement, and including RNS's own
  output at its most detailed offered level (grep-based assertion over captured output for the
  known values and for any 32-hex-character hash).
- Invalid `rpc_key` values are rejected by MeshBeacon before RNS sees them (RNS would silently fall
  back — verified).
- Container: no published ports; no host network; health endpoint reveals no identities or peers.

### 4.2 Configuration injection (hostile-input suite)

Run every user-controlled field (peer name, host, port, network name, passphrase, preset names)
through both the Supervisor-schema layer and the core validator with a corpus including:

| Class | Examples |
|---|---|
| Structure | `\n`, `\r\n`, `\r`, `[[x]]`, `[x]`, `]]`, `=`, leading/trailing spaces |
| ConfigObj syntax | `,` (list), `#` (comment), `'`, `"`, `"""`, `\\` |
| Interpolation | `%(enable_transport)s`, `$enable_transport`, `${x}` |
| Control and encoding | `\0`, `\t`, `\x1b`, Unicode line/paragraph separators (U+2028/9), right-to-left override, homoglyph hostnames, over-long values |
| Hostnames | `localhost`, trailing dot, empty label, 254+ characters, IPv6 with zone ID, IP with port appended |

Assertions:

1. Every hostile value is **rejected** with a clear message, *or* (for passphrases, where a wider
   character set is allowed) rendered so that the re-parsed config is **structurally identical** to
   the intended one: same sections, same keys, single scalar string values, no interpolation.
2. The rendered file **never** contains a section or key that was not in the intended structure —
   in particular never `AutoInterface`, `discoverable`, `discover_interfaces`,
   `autoconnect_discovered_interfaces`, `publish_ifac` or `location_cmd`.
3. Property-based fuzzing (e.g. Hypothesis) of the renderer with arbitrary Unicode strings
   maintains assertion 2 for every input that passes validation.

Phase 0 reproduced the naive-templating injection with RNS's vendored ConfigObj (architecture
§4.1); that reproduction becomes the first regression test.

### 4.3 Identity integrity

| Scenario | Expected |
|---|---|
| First start | Identity created atomically (temp file + `fsync` + rename), 0600, backup copy written, fingerprint recorded in `state.json` (not in logs) |
| Truncated / zero-length / random-bytes identity, valid backup | Restored from backup; restoration logged in words; RNS starts with the original identity (fingerprint matches) |
| Truncated identity, no valid backup | RNS **not started**; identity-problem message; file left untouched for manual recovery |
| Identity fingerprint differs from the recorded one | `needs_attention`; RNS not started; explained |
| Kill the init step at random points during first creation (repeat ≥ 1,000 times) | Never a partial identity at the final path |
| "Replace identity" option | New identity; previous one kept as `identity.replaced-<timestamp>`; log message contains **no** hashes; a restart with the option still on is refused with an explanation |
| HA backup → wipe → restore | Same identity hash |

Phase 0 verified that RNS itself overwrites a corrupt identity (architecture §4.6); a test asserts
MeshBeacon never lets RNS start in that state.

## 5. Resilience and resource tests

- Kill the RNS child: core restarts it with back-off; process health goes `restarting` →
  `running`.
- Crash loop: breaker opens after 5 failures in 15 min; after 3 openings without a stable 10-minute
  run the core enters `needs_attention`; the health endpoint **keeps returning 200** throughout
  (time is simulated in tests).
- Deterministic failures (invalid identity with no backup, fingerprint mismatch, low disk, invalid
  options): RNS never started, `needs_attention` immediately, health 200, no retries.
- Start history: 5 core starts within 30 min without a stable run → safe mode; safe mode left
  after an options change or once the window has expired.
- Core hang (test hook stops the heartbeat): health endpoint fails; a simulated Supervisor
  watchdog restart follows; repeated hangs end in safe mode, not an endless loop.
- Core exit: s6 `finish` stops the container with a non-zero code (container test).
- **Connectivity is not health:** drop the peer / remove the default route → connectivity
  `offline`; the health endpoint keeps returning success; no Supervisor restart (simulate the
  watchdog poll in test).
- Isolated node (no peers): warning logged at start and at most every 6 hours; no outbound
  connection attempts.
- Memory guard: a test hook raises reported RSS + swap above the ceiling → controlled restart.
- CPU: processes run with the configured niceness.
- Storage: fill a test `/data` to below the thresholds → warning / refusal as designed; oversized
  `cache/` cleared on start.
- Logs: a local announce flood or a debug-level RNS produces at most the configured rate; a
  "lines suppressed" summary appears.
- `SIGTERM` honoured within the Supervisor timeout.

### 5.1 Low-memory profile

The reference device has 8 GB, which would hide excessive memory use, so lightweight operation is
tested separately in CI and before release:

| ID | Test | Pass criteria |
|---|---|---|
| L1 | Container started with `--memory=256m --memory-swap=256m` (no swap), both architectures (aarch64 under QEMU in CI) | Starts, renders config, connects to an isolated test peer |
| L2 | L1 plus a bounded local announce flood against a transport-enabled instance: flooder (3,000 destinations) → peer with announce cap and ingress control **disabled** → MeshBeacon (`tests/integration/test_flood.py`, container `test_low_memory_announce_flood`) | No out-of-memory kill; memory guard restarts, if any, are logged and recover |
| L3 | L1 with transport on for 24 h on the isolated test network (release check, not every push) | No out-of-memory kill; RSS + swap stays below the 256 MB guard |
| L4 | Idle measurement in CI (amd64 and aarch64) | RSS + swap of all app processes ≤ 128 MB; a regression of more than 10 % against the previous release fails the build |

If a lower-memory physical device becomes available (feasibility Q-34), L1–L3 are repeated on it
before major releases.

## 6. Reference environment testing (before each release)

Run on the maintainer's reference device described in
[reference-environment.md](reference-environment.md): Raspberry Pi 4B, `aarch64`, Home Assistant
OS 18.5, Core 2026.11.2, Supervisor 2026.11.0, with Tailscale, AdGuard Home, Matter Server, Advanced
SSH & Web Terminal, File editor and Get HACS installed; Wi-Fi as the default interface; 5G uplink;
UPS.

Rules:

- These are **manual, maintainer-run release tests on a live Home Assistant instance**, using
  release-candidate images. They are never run by CI or by an AI agent, and never before Phase 1
  has been approved.
- Take a **full Home Assistant backup** before each test session.
- Peers used are the maintainer's own test peers or verified presets — never unverified public
  endpoints.
- **Records contain no household identifiers** (no IP or tailnet addresses, hostnames, SSIDs,
  identity hashes). Use placeholders (`<lan-ip>`, `<tailnet-ip>`, `<peer-host>`) and record
  identity *equality* as "hash unchanged: yes/no", never the hash itself.
- Each run records: MeshBeacon version, RNS version, HA OS / Core / Supervisor versions, date,
  tester, pass/fail per test, and notes.

### 6.1 Baseline

| ID | Test | Pass criteria |
|---|---|---|
| R1 | Install from the repository URL; start with defaults (no peers) | Starts; isolated-node warning; no outbound connections (check from the router or AdGuard query log: no lookups for peer hostnames) |
| R2 | Supervisor app page | Security rating 8 shown; no host network, ports, API or device access requested |
| R3 | Idle resources after 1 h | App RSS ≤ 128 MB; CPU near idle |
| R4 | Timed first run (first-run UX §7) | Median ≤ 5 min across testers |

### 6.2 Compatibility with co-installed apps

| ID | Test | Pass criteria |
|---|---|---|
| C1 | MeshBeacon running alongside Tailscale (both started, both restarted in either order) | Both healthy; no errors in either log; Tailscale connectivity unaffected |
| C2 | MeshBeacon connects to a test peer at a **tailnet address** | Records the answer to Q-8: connects (pass) or fails cleanly with a plain message (documented limitation) |
| C3 | Tailscale stopped while MeshBeacon uses a tailnet peer | MeshBeacon goes `offline`, no restart; reconnects when Tailscale returns |
| C4 | Tailscale's exit node or subnet routing enabled (if the maintainer uses them) | Reticulum peers over the internet still reachable; behaviour documented |
| C5 | MeshBeacon alongside AdGuard Home, with AdGuard serving DNS | Peer hostnames resolve; connection succeeds |
| C6 | Peer hostname blocked in AdGuard (temporary custom rule) | MeshBeacon reports a clear "cannot resolve `<peer-host>`" message; no crash or restart loop; recovers when unblocked |
| C7 | AdGuard Home stopped or restarted | DNS failure → `offline` with a plain message; recovers automatically; already-established TCP sessions survive if the resolver is not needed |
| C8 | AdGuard query log after 24 h | Only configured peer hostnames appear (evidence of no unexpected outbound connections) |
| C9 | Matter Server operating normally (a Matter device controlled) while MeshBeacon runs with transport on | No interference; no errors in either log |
| C10 | Restart Home Assistant Core and the host | All apps, including MeshBeacon, come back; MeshBeacon `online` without user action |

### 6.3 Soak tests

| ID | Test | Duration | Pass criteria |
|---|---|---|---|
| S1 | Transport **off**, one or more peers | 72 h | No monotonic RSS growth; bounded `/data` growth; log volume within rate limits |
| S2 | Transport **off**, isolated (no peers) | 24 h | Warning repeated at most every 6 h; no outbound traffic |
| S3 | **Transport on**, connected to ≥ 2 peers (at least one busy network) | **≥ 7 days** | No monotonic RSS growth after warm-up; RSS below the ceiling (no guard restarts) or guard restarts documented and explained; CPU at reduced priority and HA UI responsive throughout; `/data` growth bounded; bytes written to SSD recorded; 5G data in/out recorded per day; no peer-operator bans (e.g. Diamond limits) |
| S4 | Transport on during an RNS release-candidate upgrade (when an upgrade is due) | 72 h | As S3; identity hash unchanged after upgrade |

Recorded for each soak: RSS, **swap** and CPU at least hourly (from the periodic status line), `/data` size
daily, bytes in/out daily, restart counts by cause.

### 6.4 Internet outage recovery

| ID | Scenario | Pass criteria |
|---|---|---|
| O1 | 5G uplink disconnected for 5 min (router WAN off), Wi-Fi still up | Connectivity `offline` within the reconnection interval; **no app restart by the Supervisor**; health endpoint stays healthy; reconnects within 2 min of the uplink returning |
| O2 | 5G uplink off for 6 h | As O1; no log flood (rate limit and summaries); memory stable |
| O3 | Pi's **Wi-Fi** disconnected (access point off / Wi-Fi disabled) for 5 min | As O1 |
| O4 | Repeated flapping: uplink off/on every 2 min for 30 min | No restart storm; circuit breaker **not** triggered (connectivity is not health); reconnects at the end |
| O5 | DNS unavailable but IP routing up | Plain "cannot resolve" message; recovers when DNS returns |

### 6.5 Power outage recovery

| ID | Scenario | Pass criteria |
|---|---|---|
| P1 | Mains removed; UPS carries the Pi; mains restored before the battery runs out | No interruption; nothing to recover |
| P2 | Clean host shutdown (as a UPS low-battery shutdown would trigger, if configured), then power on | MeshBeacon starts automatically; identity hash unchanged; `online` without user action |
| P3 | **Abrupt power loss** (bypass the UPS) while MeshBeacon is running with transport on | Boots cleanly; identity hash unchanged; RNS SQLite database opens (or is rebuilt from regenerable state without identity loss); no user action needed |
| P4 | Abrupt power loss **during first start** of a fresh install (pull power within seconds of starting) | On next boot, a complete valid identity exists, or a new one is created cleanly; never a truncated identity at the final path |
| P5 | Repeat P3 five times | Same result every time |

### 6.6 Identity persistence across backup and restoration

| ID | Scenario | Pass criteria |
|---|---|---|
| B1 | Full HA backup (hot) while MeshBeacon runs with transport on → restore on the same device | Identity hash unchanged; RNS database consistent (feeds Q-7) |
| B2 | Partial backup of only the MeshBeacon app → uninstall app → reinstall → restore the app backup | Identity hash unchanged |
| B3 | Restore an **older** app backup after the identity was regenerated on purpose | The restored (older) identity is used; MeshBeacon logs that the identity changed versus its last recorded state and asks for confirmation as designed (architecture §4.6) |
| B4 | Encrypted backup restored on a **second, clean HA OS install** (spare SD card or test device) | Identity hash unchanged; works on first start |
| B5 | Backup excludes regenerable data | Archive contains `transport_identity`, `identity.backup`, rendered config; excludes `cache/` and `resources/` |
| B6 | Backup archive inspection | Documented warning confirmed: an **unencrypted** backup contains the private key in plain form |

### 6.7 Public peer verification (manual, release-time only)

Presets are verified by the maintainer against live infrastructure using checks V1–V7 in
[public peer presets §3](../research/public-peers.md#3-interoperability-and-verification-requirements).
Together with the soak tests (§6.3), these are the **only** tests that touch public networks; they are never run in CI, and their
results are recorded in the repository with date, RNS version and tester.

## 7. Supply-chain checks in CI

- Dependency install with `--require-hashes`.
- Vulnerability scanning of Python deps and image (e.g. `pip-audit`, Trivy or Grype).
- Secret scanning (GitHub secret scanning + gitleaks).
- SBOM generation and licence allow-list check.
- Image signature verification after publish.

## 8. Coverage targets

- Core: ≥ 90 % line coverage, 100 % of validation, config rendering, identity and permission code paths.
- Every bug fix lands with a regression test.
