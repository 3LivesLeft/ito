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

## v0.2.0 — Visibility (in progress, branch `feature/v0.2.0-observability`)

Lightweight, privacy-first monitoring ([feasibility and architecture](research/v0.2-observability.md),
[ADR 0006](adr/0006-local-metrics-api.md), accepted 18 Nov 2026):

- Optional, read-only, token-authenticated local status API (internal network only, off by
  default), delivered to Home Assistant by Supervisor discovery.
- HA custom integration: status, connectivity, diagnosis, per-peer connection and "connected
  since", traffic totals and rates, known paths, relayed links (forwarding indicator), announces,
  CPU, memory, Reticulum restarts, reconnections; HA's recorder provides history and statistics.
- Repair issues for "isolated node", "no peers reachable" and anything that needs attention
  (identity, options, storage, repeated failures).
- Redacted diagnostics download; an example dashboard of native HA cards.
- A **MeshBeacon sidebar panel** served by the integration ([ADR 0007](adr/0007-sidebar-panel.md),
  proposed): Overview and Diagnostics tabs, history from HA's recorder, admin-only, no third-party
  code.
- HACS compatibility **prepared, not published** ([HACS](hacs.md)).
- **Not** included: a forwarded-packet count (RNS exposes none through supported interfaces),
  identity import (deferred), any control from Home Assistant, HACS publication or releases.

## v0.3.0 — Messaging (research and architecture; not authorised for implementation)

Proposed in [v0.3 messaging](research/v0.3-messaging.md) and ADRs
[0008](adr/0008-messaging-process.md)–[0012](adr/0012-optional-propagation-node.md). **Not to be
implemented until independently reviewed and approved.**

- Text messaging over unmodified LXMF in a separate, supervised process; a separate messaging
  identity; contacts-only inbound by default.
- Persistent, bounded queue; receipts that tell "delivered" from "stored on a node"; offline
  delivery through a propagation node.
- Home Assistant: notify entities per contact, a send action with a response, event entities,
  an actionable-notification blueprint; message content never recorded by default.
- Interoperability matrix with Sideband 2.3 and Ratspeak 1.1 (also NomadNet and MeshChat where
  practical) on isolated networks.
- Optional propagation node with quotas (phase 3b). Requires `rns`/`lxmf` pins of 1.6.1/1.3.1.

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

---

## v0.2.0 acceptance criteria

Same evidence rules as v0.1.0. Container figures come from the test-only stand-in base unless
stated otherwise. **They are not Raspberry Pi validation.** Revised after independent review
(18 Nov 2026): OB-3, OB-8 and OB-11 tightened; OB-15 to OB-21 added. The physical test is
[v0.2 hardware acceptance](testing/v0.2-hardware-acceptance.md).

| ID | Criterion | Evidence type | Status |
|---|---|---|---|
| OB-1 | With default options, no API listener exists and no discovery message is sent; `config.yaml` adds only `discovery` (no `hassio_api`, `homeassistant_api`, ports or ingress). The option stays off by default permanently | Automated (integration, container, static `config.yaml`) | Met (automated) |
| OB-2 | With the option on, one discovery message carries host, port, token and certificate fingerprint, using the Supervisor token without `hassio_api`; switching the option off withdraws it | Automated (fake Supervisor) + Pi | Automated part met; real Supervisor **indicated** on the Pi (integration set up, 18 Nov); C2–C3, D5 pending |
| OB-3 | The API serves only `GET /api/v1/status`, **over TLS 1.3 only**, with a valid bearer token: 401 otherwise, 404 for other paths, 501 for other methods. Tokens ≥ 256 bits and certificates new at every start; constant-time comparison; plain HTTP not served | Automated | Met (`tests/unit/test_api.py`, `test_status_api_is_https_only_with_a_fresh_pinned_certificate`) |
| OB-4 | Served data and logs contain no identity, destination or interface hashes, peer hosts or ports, network names, passphrases, API token or Supervisor token | Automated | Met |
| OB-5 | The Supervisor token never reaches the prepare step, the certificate step or Reticulum | Automated (`/proc/<pid>/environ`) | Met (integration and container tests) |
| OB-6 | Values RNS does not provide are reported as unavailable, never zero; no forwarded-packet figure; the RNS keys read are pinned by a contract test | Automated | Met |
| OB-7 | Accuracy on isolated networks: disconnect and reconnection counted; known paths equal the path table size; a relayed link appears in transport mode | Automated (real RNS, loopback) | Met |
| OB-8 | Bounded: API ≤ 4 connections, 5 s inactivity timeout **and 10 s absolute deadline**; `/health` on its own server, ≤ 16 connections, 5 s deadline; ≤ 8 samples per rate; ≤ 10 peers; 0 bytes of metric storage | Automated | Met (trickling-client, stalled-handshake, health-bounds and rate-window tests) |
| OB-9 | Idle memory ≤ 128 MB (RSS + swap, all app processes) with the option on | Container + Pi | Container met: **70.8 MiB** on, 67.8 MiB off; Pi **78 MiB at 7 minutes** (initial, [physical results](testing/v0.2-physical-results.md)); 1-hour reading pending (B6, E1) |
| OB-10 | Collection and serving add < 0.1 % of one core on average | Container + Pi | Container met (see results); Pi pending (E1) |
| OB-11 | Integration: set up only through discovery; rediscovery updates key and fingerprint without reauthentication; state classes for long-term statistics; unavailable → unknown; repairs appear and clear; redacted diagnostics; dashboard references only real, enabled-by-default entities | Automated (HA 2026.10.4 harness) | Met (`tests/ha`, 48 tests) |
| OB-12 | The integration never imports RNS or the core; its parser accepts the core's real output; enumerations match | Automated | Met |
| OB-13 | On the reference Pi: discovered, entities populate, history fills, no new AppArmor denials, rating still 8 | Manual, physical — after the v0.1 soak (ended early with maintainer approval) | **In progress**: discovered and entities populate on the Pi ([initial results](testing/v0.2-physical-results.md)); history, AppArmor and rating not yet recorded |
| OB-14 | CI green, including both Home Assistant jobs, AppArmor-confined container tests, gitleaks and pip-audit | CI run | Met for head `ac2a2cc` (14 checks, independently confirmed); to be re-run for this branch's later commits |
| OB-15 | **Anti-spoofing:** discovery from a non-MeshBeacon slug, pointing anywhere other than the sending app's own hostname, or without a fingerprint, is refused, both in the config flow and in self-healing; a look-alike cannot change the real entry | Automated | Met (`tests/ha/test_security.py`) |
| OB-16 | **No key leaks** in app logs, HA logs (debug level), exceptions, flow listings or diagnostics, under every failure mode | Automated | Met |
| OB-17 | **Recovery without restart:** discovery succeeds after the Supervisor fails at first, is down at start, or restarts later; a missed rotation push heals within 5 minutes; repeated rotation and switching off and on work; stale keys are refused | Automated + Pi | Automated part met (`test_monitoring_reliability.py`, `test_security.py`); Pi pending (D1–D6) |
| OB-18 | **Isolation:** errors in monitoring never stop the supervision loop or restart Reticulum | Automated | Met (`test_monitoring_errors_never_reach_reticulum`) |
| OB-19 | **Floods:** 30 s of hostile traffic on both ports leaves every watchdog check answered, Reticulum connected and not restarted, and core threads and memory bounded | Automated (slow) | Met (`test_sustained_flood_and_slow_clients`) |
| OB-20 | **Recorder budget:** ≤ 2 MB/day of recorder growth, worst case, with defaults | Automated measurement + Pi | Measured about 1.9 MB/day (HA harness, file-backed SQLite); Pi pending (E3) |
| OB-21 | **Reference release:** the integration loads and populates entities on **Home Assistant 2026.11.2**, with strict typing against that release | CI (`home-assistant-release` job) | Met locally (`tools/ha_smoke_test.py`); CI see PR #3 |
| OB-22 | **Complete, bounded reads:** status responses split into any number of TLS records, TCP segments or HTTP chunks are read in full; more than 256 KiB is refused (declared or not) without buffering the excess; a truncated reply is a connection error, never partial data | Automated (real TLS on 127.0.0.1) | Met (`tests/ha/test_client_reading.py`; 9 of its tests fail against the previous single read) |
| OB-23 | **Sidebar panel:** a "MeshBeacon" sidebar entry with its own icon appears when the integration loads and goes when it unloads, for administrators only, with no configuration; the websocket command refuses non-admins | Automated (HA harness) + HA 2026.11.2 smoke | Met (`tests/ha/test_panel.py`; smoke test checks route and module) |
| OB-24 | **No third-party code or duplicate storage:** the panel's files contain no external URLs, `fetch`, `XMLHttpRequest`, `innerHTML`, `eval` or browser storage; history only from HA's recorder; static path serves only the frontend folder and no data | Automated | Met (`tests/frontend/model.test.mjs`, `tests/ha/test_panel.py`) |
| OB-25 | **States:** loading, not connected, error with retry, app unavailable, history unavailable and no history yet are each shown distinctly; unavailable values show as "—", never zero | Automated (model) + preview screenshots | Met in sandbox (model tests; `tools/panel_preview.html` scenarios) |
| OB-26 | **Layout and themes:** usable at 390 px (phone), 820 px (tablet) and 1280 px (desktop) widths in light and dark themes, with no horizontal scrolling | Preview screenshots; physical check on a phone | Sandbox met; **physical pending** (open the panel on a phone and a desktop on the Pi installation, after approval) |
| OB-27 | **Panel cost:** history fetched at most once per chart bucket (≥ 60 s) and only while visible; re-render only when MeshBeacon's own entities change | Code review + model tests | Met (sandbox); browser CPU on a low-end phone pending |
| OB-28 | **HACS-ready, not published:** `hacs.json` with known keys only, no release ZIP or release workflow, one integration, manifest complete, versions aligned | Automated | Met (`tests/unit/test_hacs.py`); HACS's own validation action is a maintainer step ([HACS](hacs.md)) |

## v0.3.0 acceptance criteria (proposed, for review)

Measured on isolated networks and on the reference Pi. "Pi" figures are release gates.

| ID | Criterion | Evidence |
|---|---|---|
| MS-1 | With messaging off: no messaging process, no `/data/messaging/` writes, no new endpoints, memory and CPU unchanged from v0.2 (±2 MiB) | Automated + Pi |
| MS-2 | The messaging identity is 0600, validated before every start, never logged, and independent of the transport identity (replacing either leaves the other unchanged) | Automated |
| MS-3 | Announces carry no display name by default, and no telemetry, location or icon fields are ever sent | Automated (inspect packed announces and messages) |
| MS-4 | Acknowledged inbound content is deleted by default; retention ≤ 30 days when chosen; `queue.db` ≤ 16 MiB under a flood | Automated |
| MS-5 | Send → `delivered` within 30 s on a loopback direct path; the same idempotency key twice gives one message | Automated (real LXMF) |
| MS-6 | Recipient offline: `stored_on_node` via `lxmd`, never reported as `delivered`; recipient later collects it; app restart mid-send resubmits | Automated |
| MS-7 | Message content and titles appear in no HA database table, log (debug level), diagnostics file or bus event; the blueprint omits content by default | Automated (HA harness + recorder inspection) |
| MS-8 | Only signature-validated messages from contacts reach HA by default; unknown or invalid senders are counted, not delivered | Automated |
| MS-9 | "Anyone" mode enforces the stamp cost; contacts with tickets are not charged | Automated |
| MS-10 | Inbound > 8 KiB, extra fields, invalid UTF-8 and floods above the rate limits are dropped and counted; nothing crashes | Automated (fuzz) |
| MS-11 | No code path turns message content into an HA action; the blueprint performs only notification and reply | Code review + test |
| MS-12 | Messaging endpoints refuse the status key, raw LXMF addresses and unknown contact IDs | Automated |
| MS-13 | Send rate limits enforced; with a long poll held, the status API still answers within 1 s | Automated |
| MS-14 | **Interoperability matrix** passes both ways with Sideband 2.3.x and Ratspeak 1.1.x (direct, opportunistic, propagated, stamped, offline cases) on an isolated network | Manual, recorded |
| MS-15 | Killing or hanging the messaging process never restarts Reticulum or interrupts the status API; it recovers within bounded back-off and pauses after 5 failures in 30 min | Automated |
| MS-16 | A corrupt `queue.db` is quarantined and a repair issue appears; transport continues | Automated |
| MS-17 | Propagation node off by default; when on: static peers only, quota respected (≤ 64 MiB default, ≤ 25 % free space), stamps enforced | Automated |
| MS-18 | Pi resources: messaging on, idle ≤ +40 MiB (app ≤ 160 MiB) and ≤ 0.5 % CPU added; stamp at the recipient's cost ≤ 30 s or a clear failure | Pi |
| MS-19 | SD-card writes ≤ 1 a second sustained under normal traffic | Automated measurement |
| MS-20 | Panel Messages tab (only when messaging is on) shows conversations and receipts, writes text only, and stores nothing in the browser | Automated + preview |
