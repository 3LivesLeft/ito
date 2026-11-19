# Roadmap

Status: **Provisional — revised after independent review; long-term direction added 19 November
2026.** Every item remains open to challenge. Completed milestones and acceptance records below are
unchanged. **v0.4 onwards are proposed milestones, not release commitments; v1.0 is unscheduled.**
Decisions of 19 November 2026: ADRs [0007](adr/0007-separate-identities.md) to
[0010](adr/0010-v0.3-scope.md).

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

The "Where it went" column records the plan when v0.1.0 was scoped ([history](#roadmap-history)).
Now: LXMF is the v0.3 messaging milestone; HA notifications are removed from committed scope;
propagation is proposed v0.5; I2P, RNode and remote automation are
[unscheduled future capabilities](#future-capabilities-unscheduled).

## v0.2.0 — Visibility (merged to `main` in PR #3; physical acceptance pending)

Lightweight, privacy-first monitoring ([feasibility and architecture](research/v0.2-observability.md),
[ADR 0006](adr/0006-local-metrics-api.md), proposed):

- Optional, read-only, token-authenticated local status API (internal network only, off by
  default), delivered to Home Assistant by Supervisor discovery.
- HA custom integration: status, connectivity, diagnosis, per-peer connection and "connected
  since", traffic totals and rates, known paths, relayed links (forwarding indicator), announces,
  CPU, memory, Reticulum restarts, reconnections; HA's recorder provides history and statistics.
- Repair issues for "isolated node", "no peers reachable" and anything that needs attention
  (identity, options, storage, repeated failures).
- Redacted diagnostics download; an example dashboard of native HA cards.
- **Not** included: a forwarded-packet count (RNS exposes none through supported interfaces),
  identity import (deferred), any control from Home Assistant, HACS publication.

## v0.3.0 — Installation and distribution (next)

Decided by the maintainer, 19 November 2026 ([ADR 0010](adr/0010-v0.3-scope.md)). **No new
application features.** The release makes MeshBeacon installable through Home Assistant's native
app installation path:

- signed, multi-arch app images and the app repository (`repository.yaml`, already present),
  added from the **App store**, with a one-click My Home Assistant link **[Verified]** (HA
  developer documentation, "Create an app repository");
- any further catalogue the maintainer names (Q-43); listing anywhere is submitted by the
  maintainer personally (CLAUDE.md rule 10);
- installation and update documentation; the v0.2 integration's installation path (Q-45).

**Gates:** every Tier A criterion (LP-1 to LP-20) and Tier B release gate (RG-1 to RG-12), the
v0.2 physical acceptance still pending (OB-2, OB-9, OB-10, OB-13, OB-17, OB-20), the naming
decision (Q-41), and the maintainer's explicit approval to publish.

## v0.3 messaging milestone — secure LXMF messaging (after v0.3.0, gated)

Secure private LXMF messaging, contacts and delivery tracking, in a later v0.3 release. It ships
only when **all** of these gates are met; the messaging design turns them into acceptance criteria.

| ID | Gate |
|---|---|
| MG-1 | **Authorisation:** sending can be restricted to callers the user explicitly approves. The Home Assistant / Supervisor capabilities this needs are identified on the HA release then current, and any permission they require is approved by ADR (hard rule 4). HA's default service-call permissions are not sufficient (maintainer decision, ADR 0010) |
| MG-2 | An ADR for the Home Assistant → core path for sending; ADR 0006's status API stays read-only |
| MG-3 | Separate messaging identity: [ADR 0007](adr/0007-separate-identities.md) validation IV-1 to IV-5 passed; transport identity unchanged on upgrade |
| MG-4 | Announcing the messaging address is an explicit opt-in ([ADR 0008](adr/0008-opt-in-publication.md)) |
| MG-5 | The process model does not prevent isolating later public services from transport ([ADR 0009](adr/0009-public-service-isolation.md), Q-35) |
| MG-6 | No message content or metadata in logs or diagnostics; storage location (Q-39), quota and backup treatment (Q-44) decided |
| MG-7 | Delivery states can express long, LoRa-scale delays (forward-compatibility review F-6) |
| MG-8 | Interoperability with Sideband, NomadNet, MeshChat and Ratspeak on isolated networks |

Removed from the committed v0.3 scope: the HA `notify` platform (its default service permissions
do not satisfy the messaging authorisation requirements; it may return only through MG-1 and its
own ADR) and the optional propagation node (now proposed v0.5).

## Long-term direction (proposed)

MeshBeacon is to grow into a free, open-source, privacy-first, decentralised **community network**
that keeps operating without the internet: communities host and discover information,
communicate and share resources over Reticulum, including compatible LoRa radio links. Home
Assistant remains a first-class deployment and management interface; the community services must
not depend on it. See the [vision](vision.md#long-term-direction) and its
[architectural principles](vision.md#architectural-principles-for-the-long-term-direction).

**These milestones are proposed, not release commitments.** Each needs its own design, ADRs and
acceptance criteria, approved by the maintainer, before implementation starts. Every public
service is subject to [ADR 0008](adr/0008-opt-in-publication.md) (opt-in announcement and
publication) and [ADR 0009](adr/0009-public-service-isolation.md) (isolated from Home Assistant
and from the transport failure domain).

| Version | Theme | Proposed content |
|---|---|---|
| v0.4 | Public offline internet | Nomad Network-compatible page hosting, browsing, publishing and discovery; lightweight content suitable for LoRa |
| v0.5 | Community services | Public bulletin boards, offline knowledge libraries, **LXMF propagation services, including the optional propagation node** (moved from v0.3), community information sharing |
| v0.6 | Voice messaging | Short push-to-talk voice bursts with low-bitrate codecs, asynchronous delivery, radio airtime limits |
| v0.7 | Resilient infrastructure | Distributed content replication, selected sensor sharing, local alerts, network resilience |
| v0.8+ | Advanced communications | *Investigation:* live push-to-talk group voice over suitable higher-bandwidth transports, intelligent transport selection, additional radio capabilities |

### Future capabilities (unscheduled)

Kept explicitly so that nothing is dropped silently. Each needs its own design and ADRs.

| Capability | Note |
|---|---|
| **RNode / LoRa radio hardware support** | Explicit future capability: RNode with explicit device mapping and regional parameter validation (UK: Ofcom IR 2030 **[Assumption]**). Device access changes the security posture and needs an ADR (hard rule 4). Needed before LoRa-aware features can be validated on air |
| Optional I2P (separate router); public-gateway investigation | Candidate for v0.7 or v0.8+ (Q-42) |
| Authenticated remote automation | Private and allow-listed, separate from public services (ADR 0009); external design review before implementation |
| Identity import from file | Requirements in architecture §4.6; relevant to principle 8 |
| TCP listener (inbound) | Later, if requested; not needed to host services over outbound links **[Assumption]** |
| Tailscale guidance (documentation only) | Once tested (feasibility Q-8) |

## v1.0.0 — Stable (unscheduled)

A stability milestone, **not scheduled and not a release commitment** ([ADR 0010](adr/0010-v0.3-scope.md)).
Criteria unchanged: external security audit, compatibility matrix, full documentation, standalone
Docker image (the basis for standalone Raspberry Pi and other Linux deployments, principle 7), and
a published RNS-upgrade policy.

## Roadmap history

Superseded plans are kept here rather than deleted.

| Date | Plan | Superseded by |
|---|---|---|
| 18 Nov 2026 | v0.3 Messaging (LXMF, HA `notify`, interop testing, optional propagation node); v0.4 Privacy and reachability (I2P, public-gateway investigation); v0.5 Off-grid (RNode); v0.6 Remote automation; v1.0 after v0.6 | Long-term direction, 19 Nov 2026 (commit `f409058`) |
| 19 Nov 2026 (`f409058`) | v0.3 "Installation and LXMF messaging" as one release, still including `notify` and the propagation node; I2P, RNode and remote automation unscheduled; v1.0 position open | ADR 0010 (this revision) |

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

---

## v0.2.0 acceptance criteria

Same evidence rules as v0.1.0. Container figures come from the test-only stand-in base unless
stated otherwise. **They are not Raspberry Pi validation.** Revised after independent review
(18 Nov 2026): OB-3, OB-8 and OB-11 tightened; OB-15 to OB-21 added. The physical test is
[v0.2 hardware acceptance](testing/v0.2-hardware-acceptance.md).

| ID | Criterion | Evidence type | Status |
|---|---|---|---|
| OB-1 | With default options, no API listener exists and no discovery message is sent; `config.yaml` adds only `discovery` (no `hassio_api`, `homeassistant_api`, ports or ingress). The option stays off by default permanently | Automated (integration, container, static `config.yaml`) | Met (automated) |
| OB-2 | With the option on, one discovery message carries host, port, token and certificate fingerprint, using the Supervisor token without `hassio_api`; switching the option off withdraws it | Automated (fake Supervisor) + Pi | Automated part met; real Supervisor pending (hardware C2–C3, D5) |
| OB-3 | The API serves only `GET /api/v1/status`, **over TLS 1.3 only**, with a valid bearer token: 401 otherwise, 404 for other paths, 501 for other methods. Tokens ≥ 256 bits and certificates new at every start; constant-time comparison; plain HTTP not served | Automated | Met (`tests/unit/test_api.py`, `test_status_api_is_https_only_with_a_fresh_pinned_certificate`) |
| OB-4 | Served data and logs contain no identity, destination or interface hashes, peer hosts or ports, network names, passphrases, API token or Supervisor token | Automated | Met |
| OB-5 | The Supervisor token never reaches the prepare step, the certificate step or Reticulum | Automated (`/proc/<pid>/environ`) | Met (integration and container tests) |
| OB-6 | Values RNS does not provide are reported as unavailable, never zero; no forwarded-packet figure; the RNS keys read are pinned by a contract test | Automated | Met |
| OB-7 | Accuracy on isolated networks: disconnect and reconnection counted; known paths equal the path table size; a relayed link appears in transport mode | Automated (real RNS, loopback) | Met |
| OB-8 | Bounded: API ≤ 4 connections, 5 s inactivity timeout **and 10 s absolute deadline**; `/health` on its own server, ≤ 16 connections, 5 s deadline; ≤ 8 samples per rate; ≤ 10 peers; 0 bytes of metric storage | Automated | Met (trickling-client, stalled-handshake, health-bounds and rate-window tests) |
| OB-9 | Idle memory ≤ 128 MB (RSS + swap, all app processes) with the option on | Container + Pi | Container met: **70.8 MiB** on, 67.8 MiB off; Pi pending (hardware B6, E1) |
| OB-10 | Collection and serving add < 0.1 % of one core on average | Container + Pi | Container met (see results); Pi pending (E1) |
| OB-11 | Integration: set up only through discovery; rediscovery updates key and fingerprint without reauthentication; state classes for long-term statistics; unavailable → unknown; repairs appear and clear; redacted diagnostics; dashboard references only real, enabled-by-default entities | Automated (HA 2026.10.4 harness) | Met (`tests/ha`, 48 tests) |
| OB-12 | The integration never imports RNS or the core; its parser accepts the core's real output; enumerations match | Automated | Met |
| OB-13 | On the reference Pi: discovered, entities populate, history fills, no new AppArmor denials, rating still 8 | Manual, physical — **after** the v0.1 soak | Not started |
| OB-14 | CI green, including both Home Assistant jobs, AppArmor-confined container tests, gitleaks and pip-audit | CI run | See PR #3 |
| OB-15 | **Anti-spoofing:** discovery from a non-MeshBeacon slug, pointing anywhere other than the sending app's own hostname, or without a fingerprint, is refused, both in the config flow and in self-healing; a look-alike cannot change the real entry | Automated | Met (`tests/ha/test_security.py`) |
| OB-16 | **No key leaks** in app logs, HA logs (debug level), exceptions, flow listings or diagnostics, under every failure mode | Automated | Met |
| OB-17 | **Recovery without restart:** discovery succeeds after the Supervisor fails at first, is down at start, or restarts later; a missed rotation push heals within 5 minutes; repeated rotation and switching off and on work; stale keys are refused | Automated + Pi | Automated part met (`test_monitoring_reliability.py`, `test_security.py`); Pi pending (D1–D6) |
| OB-18 | **Isolation:** errors in monitoring never stop the supervision loop or restart Reticulum | Automated | Met (`test_monitoring_errors_never_reach_reticulum`) |
| OB-19 | **Floods:** 30 s of hostile traffic on both ports leaves every watchdog check answered, Reticulum connected and not restarted, and core threads and memory bounded | Automated (slow) | Met (`test_sustained_flood_and_slow_clients`) |
| OB-20 | **Recorder budget:** ≤ 2 MB/day of recorder growth, worst case, with defaults | Automated measurement + Pi | Measured about 1.9 MB/day (HA harness, file-backed SQLite); Pi pending (E3) |
| OB-21 | **Reference release:** the integration loads and populates entities on **Home Assistant 2026.11.2**, with strict typing against that release | CI (`home-assistant-release` job) | Met locally (`tools/ha_smoke_test.py`); CI see PR #3 |
