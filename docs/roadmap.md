# Roadmap

Status: **Provisional — revised after independent review.** Every item remains open to challenge.

## Phase 0 — Research and foundations (complete once PR #1 is merged)

Documentation only. **Exit:** maintainer approval of PR #1, including the review amendments
(licence Apache-2.0, name retained with conditions, presets policy, security clarifications,
narrowed v0.1.0 scope).

## v0.1.0 — A reliable, installable Reticulum node

**Deliberately small.** The goal is one thing done well: a Reticulum node that installs in minutes,
stays up, keeps its identity and explains itself in plain language.

In scope:

1. Installable Home Assistant app (formerly add-on) for `aarch64` and `amd64`, `stage:
   experimental`.
2. Unmodified RNS (pinned) as a supervised child process running as a non-root user.
3. **Simple configuration:** optional verified public peer presets (none selected by default) and
   custom outbound TCP peers (host, port, optional network name and passphrase); log detail.
4. **Persistent identity:** atomic creation, validation before every start, verified backup copy,
   no silent replacement, explicit regenerate option.
5. **Optional transport mode**, off by default, explained in plain language.
6. **Basic diagnostics:** startup report and periodic status lines in the app log; process-health
   endpoint for the Supervisor watchdog; separate connectivity status messages, including the
   isolated-node warning.
7. Resource guards: memory, CPU priority, storage, log rate.

Explicitly **out of scope** for v0.1.0 (moved or deferred):

| Item | Where it went | Why |
|---|---|---|
| TCP listener (inbound) | Later, if requested | Exposes a port; not useful behind CGNAT; complicates UX |
| HA entities, dashboards | v0.2 | Needs the integration and local API |
| Identity import from file | v0.2 | Needs an extra file-transfer path and permissions |
| LXMF, notifications, propagation | v0.3 | |
| I2P | v0.4 | |
| RNode / LoRa | v0.5 | |
| Remote automation | v0.6 | |
| Raw RNS configuration | Not planned | Would bypass validation and privacy defaults |

## v0.2.0 — Visibility

- HA custom integration (HACS) with a token-authenticated local API.
- Entities: process health, connectivity state, per-peer status, RX/TX bytes, memory.
- Repair issues for "isolated node", "no peers reachable", "identity problem".
- Redacted diagnostics download; identity import.

## v0.3.0 — Messaging

- LXMF send/receive; HA `notify` platform (HA composes plaintext; LXMF encrypts end to end — must
  be documented).
- Interoperability testing with Sideband, NomadNet, MeshChat and Ratspeak.
- Optional propagation node with disk quota.

## v0.4.0 — Privacy and reachability

- Optional I2P via a separate router; investigate public gateway hosting behind CGNAT.
- Tailscale guidance (no code needed) is documented from v0.1 onwards once tested (feasibility
  Q-8).

## v0.5.0 — Off-grid

RNode support with explicit device mapping and regional parameter validation. First version that
*optionally* uses extra hardware.

## v0.6.0 — Remote automation

Authenticated, allow-listed remote commands with replay protection — external design review
**before** implementation.

## v1.0.0 — Stable

External security audit, compatibility matrix, full documentation, standalone Docker image, and a
published RNS-upgrade policy.

---

## v0.1.0 acceptance criteria

There are two tiers. **Local prototype criteria** (tier A, `LP-n`) define the first working milestone: a
locally built MeshBeacon running on the maintainer's Raspberry Pi and connecting to a manually
configured peer. **Public release gates** (tier B, `RG-n`) must *also* be met before any image is
published or a release is announced. A criterion is marked complete only with evidence (test
output, log extract with identifiers removed, or a signed-off manual test record). **Emulated
aarch64 (QEMU) results never count as physical Raspberry Pi validation.**

Status values: *Not started* · *In progress* · *Met (evidence: …)* · *Not met*.

### Tier A — Local prototype (Phase 1 milestone)

| ID | Criterion | Evidence type | Status |
|---|---|---|---|
| LP-1 | App builds for `amd64` and `aarch64` in CI | CI run | Met (CI run 10, commit `59c1f22`: both images built against the pinned HA base image; aarch64 under QEMU) |
| LP-2 | Installs as a **local app** on the reference Pi (HA OS 18.5, `aarch64`) and starts — *maintainer-run, physical* | Manual record | **Met (start-up)** — 0.1.1 installed as a local app and started on the reference Pi (HA OS 18.5, Supervisor 2026.11.0, aarch64) under its AppArmor profile, 18 Nov 2026: s6-overlay, root init and core started; identity created; isolated-node warning shown. (0.1.0 had failed at start-up — see Phase 1 results §3.2.) Peer connection on the Pi is LP-4 |
| LP-3 | With default options: no outbound connections; isolated-node warning in the log | Automated container test + manual check on the Pi | Automated part met (container test `test_defaults_non_root_permissions_health_and_no_connections`; integration test: no sockets at all in the RNS process); manual Pi check pending |
| LP-4 | Connects to a **manually configured** peer, logs a plain "connected" message, reconnects after the peer restarts | Automated isolated-network test + manual check on the Pi | Automated part met (`test_connects_reconnects_without_restarting`, container `test_connects_to_peer_on_internal_network`); manual Pi check pending |
| LP-5 | Transport mode off by default; can be switched on and off | Automated test | Met (automated: default in `config.yaml` and settings; transport on/off rendering tests) |
| LP-6 | Identity: atomic creation; validation before every RNS start; restore from verified backup; refuse silent regeneration; explicit replacement keeps the old identity | Automated tests (testing strategy §4.3) | Met (automated: `test_identity.py`; the whole replacement transaction is crash-tested by injecting a failure before each write, `test_identity_replacement.py`) |
| LP-7 | Interrupted initialisation never leaves a partial identity (≥ 1,000 randomised kills) | Automated test | Met (automated: 1,000 randomised kills of the atomic-write primitive; 30 randomised kills of the real first-start step) |
| LP-8 | Independent random `rpc_key`, validated before use | Automated test | Met (automated) |
| LP-9 | Hostile-input suite passes; rendered config is structurally exact | Automated tests (testing strategy §4.2) | Met (automated: hostile-input regressions and property-based fuzzing) |
| LP-10 | Files 0600 / directories 0700; core and RNS run as non-root `meshbeacon` | Automated container test | Met (container tests on the real HA base image in CI, amd64 and emulated aarch64) |
| LP-11 | `config.yaml` requests no host network, ports, Supervisor/Core API, `auth_api`, devices, extra capabilities, `full_access` or Docker API; AppArmor profile present | Automated lint of `config.yaml` | Met — `config.yaml` (static test); AppArmor profile tested statically, **under enforcement in CI** (amd64 runner) and **in use on the reference Pi** (0.1.1 started confined by `local_meshbeacon`) |
| LP-12 | Recovery is bounded: back-off, breaker, `needs_attention`, start-history safe mode; health stays 200 for connectivity and deterministic failures | Automated tests (testing strategy §5) | Met (automated: policy unit tests, crash-loop/stall/safe-mode integration tests, container crash test); slow or timed-out preparation keeps health at 200 |
| LP-13 | Connectivity status is reported separately from process health | Automated test | Met (automated) |
| LP-14 | No key material, RPC key, passphrase, token or identity/destination hash in logs at any offered level | Automated log assertions | Met (automated: detailed log level with transport on, passphrase and IFAC; RNS output contained hashes and they were redacted) |
| LP-15 | Log forwarding is rate-limited; storage guard and memory guard work | Automated tests | Met (automated: rate limiter, memory guard, storage floor, cache cap) |
| LP-16 | Idle memory ≤ 128 MB (RSS + swap, all app processes) in CI on amd64 and under QEMU aarch64 | CI measurement | Partly met — amd64 **65.2 MiB** in CI (native, real HA base). aarch64 under QEMU read **130.3 MiB**, which includes emulator overhead and is not a valid measurement; the physical Pi figure (RG-1) decides this criterion |
| LP-17 | Low-memory profile L1–L2 (256 MB limit, no swap) | CI | Met — L1 and L2 (amd64 container, 256 MB limit, no swap: 3.26 MB of announces delivered, app peak 68.1 MiB, no OOM kill; also as an isolated integration test). Not run under QEMU (too slow to be meaningful); L3 (24 h) is release gate RG-3 |
| LP-18 | CI green: lint, type check, unit, integration, container security, dependency vulnerability scan, secret scan, licence check, SBOM generation | CI run | Met (CI run 10: lint, mypy, shellcheck, hadolint, isolated tests, container tests on both architectures, licence check over a real SBOM, image scan with no critical findings, pip-audit, gitleaks) |
| LP-19 | CI makes no connection to public Reticulum peers (isolated network only) | CI configuration review + network-policy test | Met (CI runs the suite in a container with `--network none`; container tests use an internal Docker network) |
| LP-20 | `DOCS.md`: install as a local app, configure a peer, transport mode, privacy, backups contain the private key, restore, experimental status | Review | Drafted (`meshbeacon/DOCS.md`); maintainer review pending |

### Tier B — Public release gates (before publishing images or announcing a release)

All of tier A (LP-1 to LP-20), plus:

| ID | Gate | Owner | Status |
|---|---|---|---|
| RG-1 | Idle memory ≤ 128 MB measured **on the physical reference Pi** after 1 h | Maintainer | Not started |
| RG-2 | Reference-environment tests R1–R4, C1–C10, S1–S4 (including ≥ 7 days with transport on), O1–O5, P1–P5, B1–B6 pass on the physical Pi | Maintainer | Not started |
| RG-3 | Low-memory profile L3 (24 h, transport on) | CI / maintainer | Not started |
| RG-4 | Timed first-run test: median ≤ 5 min, nobody over 10 min, ≥ 3 people new to Reticulum | Maintainer | Not started |
| RG-5 | Supervisor security rating 8 shown for the published app — recorded as a target met, **not** as evidence of security | Maintainer | Not started |
| RG-6 | Image Cosign-signed; SBOM attested; dependencies hash-pinned; base image digest-pinned | CI | Not started |
| RG-7 | Distribution compliance: `THIRD_PARTY_NOTICES` with full Reticulum License text; GPL corresponding-source bundle; licence allow-list (licensing O1–O7; Q-17, Q-19) | Maintainer + CI | Not started |
| RG-8 | Trademark register searches (UK IPO, EUIPO, WIPO, USPTO, MyIPO) — Q-23 | Maintainer | Not started |
| RG-9 | Courtesy contact with the existing MeshBeacon project; outcome recorded — Q-29 | Maintainer | Not started |
| RG-10 | Public peer presets: only if verified (V1–V7, two independent operators, operator consent — Q-13, Q-28); otherwise none shipped | Maintainer | Not started |
| RG-11 | Private vulnerability reporting enabled — Q-27 | Maintainer | Not started |
| RG-12 | AI assistance disclosed; every merged change reviewed by the named human maintainer | Maintainer | Not started |
