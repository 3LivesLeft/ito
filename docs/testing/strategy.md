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
| Hardware | Raspberry Pi 4B, HA OS, real network; soak test | Manual + scripted checks | Before release |
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
- No private key bytes (hex or base64 of the 64-byte identity), RPC key, passphrase or token
  appears in any log at any offered log level (grep-based assertion over captured output).
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
| First start | Identity created atomically (temp file + `fsync` + rename), 0600, backup copy written, hash recorded |
| Truncated / zero-length / random-bytes identity, valid backup | Restored from backup; logged; RNS starts with the original hash |
| Truncated identity, no valid backup | RNS **not started**; identity-problem message; file left untouched for manual recovery |
| Identity hash differs from recorded hash | Refuse to start; explain |
| Kill the init step at random points during first creation (repeat ≥ 1,000 times) | Never a partial identity at the final path |
| "Replace identity" option | New identity; old and new hashes logged; option resets itself |
| HA backup → wipe → restore | Same identity hash |

Phase 0 verified that RNS itself overwrites a corrupt identity (architecture §4.6); a test asserts
MeshBeacon never lets RNS start in that state.

## 5. Resilience and resource tests

- Kill the RNS child: core restarts it with back-off; process health goes `restarting` →
  `running`.
- Crash loop: circuit breaker opens after the configured failures; app stays up; health endpoint
  reports failure only in that state.
- **Connectivity is not health:** drop the peer / remove the default route → connectivity
  `offline`; the health endpoint keeps returning success; no Supervisor restart (simulate the
  watchdog poll in test).
- Isolated node (no peers): warning logged at start and at most every 6 hours; no outbound
  connection attempts.
- Memory guard: a test hook raises reported RSS above the ceiling → controlled restart.
- CPU: processes run with the configured niceness.
- Storage: fill a test `/data` to below the thresholds → warning / refusal as designed; oversized
  `cache/` cleared on start.
- Logs: a local announce flood or a debug-level RNS produces at most the configured rate; a
  "lines suppressed" summary appears.
- `SIGTERM` honoured within the Supervisor timeout.

## 6. Hardware and soak testing (before each release)

On the target Raspberry Pi 4B (HA OS, aarch64, SSD, Ethernet, 5G/CGNAT):

- Install from the published, signed image; verify Supervisor security rating.
- 72-hour soak with transport off, then with transport on, connected to user-chosen peers:
  record RSS, CPU, SSD writes, data usage.
- Power-cut/UPS test: identity and SQLite state survive; clean recovery.
- HA backup and restore (hot): identity preserved; node address unchanged.
- Network loss and recovery (unplug Ethernet / disable 5G).
- Timed first-run usability test with people new to Reticulum (first-run UX §7).

### 6.1 Public peer verification (manual, release-time only)

Presets are verified by the maintainer against live infrastructure using checks V1–V7 in
[public peer presets §3](../research/public-peers.md#3-interoperability-and-verification-requirements).
These are the **only** tests that touch public networks, they are never run in CI, and their
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
