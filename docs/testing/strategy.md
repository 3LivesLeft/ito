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

- Identity, config and token files are `0600`; directories `0700` — after first start, after
  restart and after an RNS-initiated rewrite.
- No private key bytes (hex or base64 of the 64-byte identity) and no tokens appear in any log,
  diagnostics output or API response (grep-based assertion).
- Rendered RNS config never contains `AutoInterface`, `discoverable`, `discover_interfaces`,
  `autoconnect_discovered_interfaces`, `publish_ifac`, or `location_cmd` unless the corresponding
  opt-in is set (and in v0.1, never).
- Missing/corrupt identity with prior state → refuses to start with a clear message.
- Container: runs without extra capabilities; no published ports; local API rejects missing or
  wrong tokens.
- Invalid `rpc_key` is rejected by MeshBeacon before RNS sees it (RNS would silently fall back).

## 5. Resilience tests

- Kill the RNS child: core restarts it with back-off; health reports correctly.
- Repeated crash loop: circuit breaker opens; app stays up and reports `unhealthy`.
- Simulated internet loss (drop the server): state goes `degraded`, no restart storm.
- Memory guard: a test hook raises reported RSS above the ceiling → controlled restart.
- `SIGTERM` honoured within the Supervisor timeout.

## 6. Hardware and soak testing (before each release)

On the target Raspberry Pi 4B (HA OS, aarch64, SSD, Ethernet, 5G/CGNAT):

- Install from the published, signed image; verify Supervisor security rating.
- 72-hour soak with transport off, then with transport on, connected to user-chosen peers:
  record RSS, CPU, SSD writes, data usage.
- Power-cut/UPS test: identity and SQLite state survive; clean recovery.
- HA backup and restore (hot): identity preserved; node address unchanged.
- Network loss and recovery (unplug Ethernet / disable 5G).

## 7. Supply-chain checks in CI

- Dependency install with `--require-hashes`.
- Vulnerability scanning of Python deps and image (e.g. `pip-audit`, Trivy or Grype).
- Secret scanning (GitHub secret scanning + gitleaks).
- SBOM generation and licence allow-list check.
- Image signature verification after publish.

## 8. Coverage targets

- Core: ≥ 90 % line coverage, 100 % of config rendering and permission code paths.
- Every bug fix lands with a regression test.
