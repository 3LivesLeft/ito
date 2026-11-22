# Threat model

Status: **Draft — revised after independent review** · Scope: v0.1.0 in detail; later versions
in outline. Method: assets → trust boundaries → threats (STRIDE) → controls. Verified facts
reference the [feasibility study](../research/feasibility.md) and
[architecture](../architecture.md).

> **The Supervisor security rating of 8 is a target, not proof of security.** It is computed from
> a handful of declared settings (AppArmor profile, ports, host network, capabilities, API roles,
> signing). It says nothing about the correctness of MeshBeacon's code, its input validation, its
> handling of secrets, or the security of RNS. Security claims must rest on the controls and tests
> below and, before v1.0, on an external audit.

## 1. Assets

| ID | Asset | Why it matters |
|---|---|---|
| A1 | **Transport identity private key** (`storage/transport_identity`, 64 raw bytes) | Node identity when transport is on; default RPC-key seed. Compromise = impersonation; loss = new node address. |
| A2 | LXMF delivery identity (v0.3) | Decrypts messages addressed to the user. |
| A3 | RNS RPC key; IFAC passphrases for private peers; (v0.2) local API token | Control of the RNS instance; access to private networks. |
| A4 | Home Assistant itself (availability, data, configuration) | MeshBeacon must not become a path into, or a burden on, HA. |
| A5 | User's IP address, approximate location, network topology | Privacy. |
| A6 | Message content and metadata (v0.3) | Privacy. |
| A7 | Host resources (RAM, CPU, SSD space and wear, 5G data allowance) | HA availability; the user's bill. |
| A8 | The shared Reticulum network | Good network citizenship. |
| A9 | Supply chain (images, dependencies, CI secrets) | Trust in every installation. |

## 2. Trust boundaries

```text
 [Public / private Reticulum peers] ──B1── [MeshBeacon container: init(root) → core → RNS child (meshbeacon user)]
 [HA UI: user-entered options] ──B7──► /data/options.json ──► init/core
 [Supervisor: watchdog, backups] ──B5── /data, health endpoint
 [Other apps on host] ──B4── namespaces, abstract sockets
 [HA Core + integration (v0.2)] ──B2── local API
 [Browser: HA frontend + MeshBeacon panel (v0.2, ADR 0007)] ──B8── HA websocket (logged in)
 [Supervisor ingress proxy (proposed, ADR 0013)] ──B11── built-in UI listener (plain HTTP, read-only)
 [CI, registry, PyPI, AI tools] ──B6── source and image build
 [Supervisor per-app socket (newer Supervisors)] ──B12── discovery relay (root) ◄── link opened by root, held by core (meshbeacon user)
 [App store and Marketplace: this GitHub repository, GHCR images] ──B13── what users install and update
```

## 3. Threats and controls (v0.1)

| ID | Boundary | STRIDE | Threat | Control | Status |
|---|---|---|---|---|---|
| T1 | B5 | I | Private key world-readable inside the container (RNS writes 0644 — **verified**) | `umask 077`; init repairs 0600/0700 before each start; non-root service user; tests | Planned |
| T2 | B5 | I | Private key in an unencrypted HA backup | Document; recommend encrypted backups | Planned |
| T3 | — | I | Key material, RPC key, passphrases or **identity/destination hashes** in logs (RNS itself prints identity hashes at level 5 — verified) | Never log them, including during first start, restoration and explicit replacement; RNS log level ≤ 4 by default; redaction of `<32 hex>` hashes and key-length blobs in forwarded RNS output; CI log assertions | Planned |
| T4 | B4 | S/E | Other host-network processes reach RNS abstract sockets (**verified** behaviour) | `host_network: false`; unique `instance_name`; explicit `rpc_key` | Planned |
| T5 | B4 | E | RPC key derivable from the identity file; invalid `rpc_key` silently falls back (**verified**) | Generate and validate the hex key ourselves before rendering | Planned |
| **T6** | B1 | I | **IP address and traffic volume visible to public peer operators** | No default peer; opt-in presets with privacy notice; custom peers always available ([ADR 0004](../adr/0004-public-peer-presets.md)) | Implemented (network selector; release-gated) |
| T7 | B1 | I | Publishing gateway address/location via interface discovery | Discovery options never rendered in v0.1 | Planned |
| T8 | B1 | T/E | Auto-connecting to untrusted discovered interfaces; LAN discovery | Never rendered; `AutoInterface` off | Planned |
| T9 | B1 | D | Announce/path-request floods exhaust memory/CPU | Transport off by default; RNS native ingress control/announce cap; RSS watchdog; `nice` | Planned |
| T10 | B1 | D | 5G data exhaustion as a transport node | Transport opt-in with explanation; byte counters; optional data warning | Planned (warning only) |
| T11 | B2 | S | Unauthenticated local API (v0.2) | Off by default, permanently. When on: TLS 1.3 with a pinned per-start certificate, a 256-bit bearer token compared in constant time, internal network only, no published port, read-only ([ADR 0006](../adr/0006-local-metrics-api.md)) | Implemented in v0.2 (tests `tests/unit/test_api.py`, `tests/integration/test_metrics_rns.py`, container test) |
| T12 | B2 | E | Excess HA permissions | No `homeassistant_api`, `hassio_api`, `auth_api` in v0.1 | Planned |
| **T13** | B4 | E | Container escape or host compromise; compromise of a root process | Non-root `meshbeacon` user for core and RNS; root limited to a small init step; no extra capabilities; AppArmor profile; no Docker socket | Planned |
| T14 | B6 | T | Malicious or compromised dependency or base image | Hash-pinned deps; digest-pinned base; signed images; SBOM; vulnerability scanning; reviewed dependency updates | Planned |
| T15 | B6 | I | Secrets leaked in repository or CI | GitHub secret scanning + push protection; gitleaks in CI; minimal CI token permissions | Planned |
| **T16** | B5 | R/D | **Silent identity replacement**: RNS overwrites a corrupt identity with a new one (**verified**) — e.g. after a power cut during first write | MeshBeacon creates the identity atomically; validates before every start and never starts RNS on failure; verified backup copy; identity-hash tracking; explicit regenerate option only (architecture §4.6) | Planned |
| **T17** | B7 | T/E | **Configuration injection** via peer name, host, network name or passphrase — newline injects a new interface, comma creates a list, `%(..)s` interpolates (**verified**) | Schema regex; core allow-list validation; ConfigObj object API only; round-trip structural check; hostile-input test suite (architecture §4.1) | Planned |
| **T18** | B5 | D | **Restart loops** between the internal circuit breaker and the Supervisor watchdog, or caused by tying health to connectivity (Supervisor restarts are unbounded in number — **verified**) | Health fails only when the core is unresponsive; deterministic failures stop immediately; bounded breaker; persisted start history → safe mode ([ADR 0005](../adr/0005-bounded-recovery.md)) | Planned |
| **T19** | — | D | **Log flooding** fills journald / wears SSD | Rate-limited log forwarding; level ≤ 4; periodic summaries instead of per-event lines | Planned |
| **T20** | B5 | D | **Storage exhaustion** on `/data` (cache, resources, SQLite growth) | Free-space checks; size caps on regenerable directories; soak test | Planned |
| **T21** | B1 | D | **Dependence on one preset operator**, or a preset operator going rogue or offline | ≥ 2 independent verified operators before presets ship; presets are data and can be removed; custom peers always available | Planned |
| **T22** | B1 | S | **Tampered or incorrect preset data** (wrong host/port) | Presets reviewed in pull requests, verified V1–V7 before each release (enforced by `tools/check_release.py`), shipped inside the signed image; validated like own peers before rendering | Implemented (V1–V7 pending) |
| T23 | B1 | T | Malicious peer exploits an RNS parsing bug | Track RNS releases; container hardening limits blast radius | Accepted residual risk |
| T24 | — | — | Upstream RNS unmaintained or slow to fix (mirror-only — **verified**) | Release monitoring; compatibility tests; ADR 0001 review triggers | Accepted residual risk |
| **T26** | B4 | I/E | **High-privilege co-installed apps** (e.g. an SSH/terminal app with protection mode disabled) can reach the Docker daemon and read any app's `/data`, including the identity (**[Assumption]**) | Outside MeshBeacon's control: documented in `DOCS.md` and SECURITY.md; recommend keeping protection mode enabled | Accepted residual risk (documented) |
| **T27** | B1 | I/D | **DNS resolver** (e.g. AdGuard Home) logs peer lookups or blocks a peer hostname | Document; plain "cannot resolve" message with no restart loop; reference tests C5–C8 | Planned |
| **T28** | B2 | I | **Another app on the internal network reads the status API** | Bearer token; no listener while the option is off. The token and certificate fingerprint reach HA Core only through Supervisor discovery, which other apps cannot read through the Supervisor API (verified, Supervisor `e610ca8`). **Correction (19 Nov 2026):** the app posts the discovery message to `http://supervisor` over **plain HTTP on the internal bridge**. That request carries the status token, the fingerprint and the app's `SUPERVISOR_TOKEN` (`core/meshbeacon/api.py`, `SUPERVISOR_URL` and `Discovery._request`). An app able to observe that bridge (the `NET_RAW` spoofing of T34) could capture them. **Impact in v0.2:** the status token allows **reading** the non-identifying status only, until the next app start; the fingerprint cannot impersonate the API (no private key); the `SUPERVISOR_TOKEN` grants only what MeshBeacon's manifest allows (discovery; no `hassio_api`), and T35's host check stops a redirect. Accepted residual (RR-9a). **No write-capable credential may ever be sent this way** | Implemented (v0.2); residual RR-9a |
| **T29** | B2 | I | **Token leaks** through logs, exceptions, flow listings, diagnostics or backups | Token in memory only in the app; never logged by app or integration (tested under every failure mode with debug logging); diagnostics redact it; rotated every start. HA's config entry holds it in plain JSON, so it is in `/config` and HA backups until the next app start (residual RR-1) | Implemented (v0.2); residual documented |
| **T30** | B2 | D | **API request flood or slow clients** starve the core or the watchdog | API: ≤ 4 connections, 5 s inactivity timeout, 10 s absolute deadline, pre-built snapshot. `/health` on its own server: ≤ 16 connections, 5 s deadline. Errors counted, not printed. 30 s flood test: watchdog answered throughout, Reticulum unaffected | Implemented (v0.2); residual RR-2 (sustained flood above 16 connections) |
| **T31** | B2 | I | **Identifier disclosure** through metrics (hashes, peer hosts, network names, passphrases) | Allow-listed counters only; no hosts, network names or hashes in the snapshot (asserted in tests); peer names only | Implemented (v0.2) |
| **T32** | B4 | E | **Supervisor token reaches Reticulum** or the prepare step | Removed from the child environment; verified by reading `/proc/<pid>/environ` in integration and container tests | Implemented (v0.2) |
| **T33** | B2 | T | **Misleading metrics** (invented or wrongly reset values) mislead diagnosis | Unavailable values are `null` and shown as unknown; no forwarded-packet figure (RNS exposes none); "Links relayed for others" explained as not packets; contract test pins the RNS keys | Implemented (v0.2) |
| **T34** | B2 | I/T/S | **Interception or impersonation on the internal network.** Apps keep `NET_RAW` unless the Supervisor's `app_drop_net_raw` flag is on (verified, default off), so an app can ARP-spoof and read or alter plain HTTP | TLS 1.3; throwaway certificate per start; fingerprint delivered by discovery and pinned before the token is sent | Implemented (v0.2) |
| **T35** | B2 | S/T | **Discovery spoofing**: another app declares the `meshbeacon` service to redirect the integration or capture credentials | Only MeshBeacon slugs; host must be the sending app's own hostname; fingerprint required; entries keyed by the slug the Supervisor sets; a look-alike needs confirmation naming app and slug | Implemented (v0.2); residual RR-3 |
| **T36** | B5 | D | **Monitoring failure disturbs Reticulum** | Every metrics call, snapshot and discovery step isolated from the supervision loop (a defect of this kind was found and fixed in review) | Implemented (v0.2) |
| **T37** | B2 | D/T | **Truncated or oversized status response**: one stream read returns only what has arrived, so a fragmented reply was rejected, and an oversized one was misreported (found in the v0.2 review) | `read_bounded()` reads until end of stream, never more than 256 KiB + 1 byte, and refuses a declared oversize before reading; identity encoding; 10 s deadline. Tested over real TLS with 1-byte pieces, chunked, length-less, exact-limit, oversize and truncated replies | Implemented (v0.2, `tests/ha/test_client_reading.py`) |
| **T38** | B8 | T/E | **Script injection through peer names or messages** in the panel (a peer name is user-chosen and travels through the app) | Every value written with `textContent`, SVG built element by element; a test forbids `innerHTML`, `eval` and similar in the panel's files; preview checked with a hostile name | Implemented (v0.2) |
| **T39** | B8 | I | **Panel exposes data to the wrong users or to anyone on the LAN** | Panel and its websocket command are admin-only; the command returns only entity IDs and peer names; values travel only over HA's logged-in websocket; the static files (fetchable without login, as all HA frontend files are) hold no data, which a test checks | Implemented (v0.2) |
| **T40** | B8 | I | **Third-party code or CDN requests** in the panel (tracking, supply chain) | Plain module, no dependencies, no build step; a test fails on any external URL, `fetch`, `XMLHttpRequest` or dynamic remote import | Implemented (v0.2) |
| **T41** | B8 | I/D | **A second history store** (browser storage) or extra load on HA from the panel | No browser storage (tested); history only from HA's recorder, fetched at most once per chart bucket (≥ 60 s) and only while the page is visible | Implemented (v0.2) |
| **T42** | B8 | T | **Static path serves more than intended** (for example the integration's other files) | Only `custom_components/meshbeacon/frontend/` is mapped; traversal attempts return 400/403/404 (tested) | Implemented (v0.2) |
| **T25** | B6 | — | **AI-tool data use**: RNS source given to an AI tool whose provider trains on inputs would risk breaching the Reticulum License's AI condition | Project rules in licensing §6.4: training opted out; documentation rather than source; no datasets | Planned (process control) |

## 4. Later versions (outline)

- **v0.2 local API and integration:** implemented as T11 and T28–T37 ([ADR 0006](../adr/0006-local-metrics-api.md));
  sidebar panel as T38–T42 ([ADR 0007](../adr/0007-sidebar-panel.md)).
  Identity import is deferred beyond v0.2.
- **v0.3 messaging:** proposed threats T43–T58 below (awaiting independent review, nothing implemented). Baseline: LXMF identity 0600; no message content in logs or diagnostics; document that
  HA composes notifications in plaintext before LXMF encrypts them; propagation node opt-in with
  disk quota.
- **Long-term direction (proposed v0.4+):** public community services need their own threat
  analysis before design (principles 4 and 5; [forward-compatibility review](../research/long-term-direction.md)).
  The three items below are now unscheduled; their version labels record the earlier plan.
- **v0.4 I2P / public gateway:** separate I2P router; public gateway only with RNS native filters,
  stamps enforcement, blackhole sources and a clear exposure statement.
- **v0.5 RNode:** device access lowers isolation; validate LoRa parameters against regional rules
  (UK 868 MHz: Ofcom IR 2030 — **[Assumption]**, to confirm).
- **v0.6 remote commands (highest risk):** sender authentication by LXMF identity *and* allowlist;
  per-command allowlist mapped to fixed HA actions (no free-form service calls, templates or
  shell); persisted replay protection; rate limiting; audit log; optional confirmation; no
  safety-critical actions by default; external design review before implementation.

### 4.0 Built-in interface through Ingress: proposed threats (ADR 0013; validation in progress)

| ID | Boundary | STRIDE | Threat | Proposed control |
|---|---|---|---|---|
| T59 | B11 | S/E | **Ingress header trust bypass**: another app or LAN client sends `X-Ingress-Path` or `X-Remote-User-*` to skip HA's login (a real class of bug elsewhere) | Accept connections only from `172.30.32.2`, checked on the socket peer; never trust forwarded or ingress headers for access; no published port |
| T60 | B11 | I/T | **Plain-HTTP hop** read or altered by a `NET_RAW` app performing ARP spoofing (as T34) | Read-only; the v0.2 snapshot only (no secrets, hashes, hosts); document `app_drop_net_raw`; residual RR-9. Pending V-1 |
| T61 | B11 | I/E | **Confidentiality of the plain-HTTP hop** beyond MeshBeacon's own data | **Confirmed from Supervisor 2026.11.0 source; blocking.** Not mitigable inside the app; read-only is **not** a mitigation. Details under responsible disclosure; Ingress not enabled ([options](../research/secure-interface-options.md)) |
| T65 | B11 | T/E | **Integrity of Ingress content** on an unprotected hop (details under responsible disclosure) | Blocking for any Ingress use until the hop is protected upstream (option B) |
| T62 | B11 | E/T | **An action through Ingress** (write, configuration, message) forged on the unprotected hop | No actions through Ingress, permanently, while the hop is plain HTTP; writes only on the pinned-TLS path (ADR 0010, proposed) |
| T63 | B11 | D | **Ingress listener flood** affects the core or watchdog | `BoundedHTTPServer` (≤ 4 connections, deadlines), separate from `/health`; page polls only while visible |
| T64 | B8/B11 | T | **Script injection or clickjacking** in the built-in UI | `textContent` only (T38); CSP `default-src 'self'; frame-ancestors 'self'`; `nosniff`; no third-party code |

### 4.0a v0.3 installation and distribution (M1; implemented unless marked)

| ID | Boundary | STRIDE | Threat | Control | Status |
|---|---|---|---|---|---|
| T67 | B13/B6 | T/E | **A compromised release or image** reaches every installation through the normal update | Base image by digest, packages by hash, actions by SHA; reproducible builds compared in CI (`tools/verify_image.py`); SBOM and provenance attestations; release order and checks in [releasing](../releasing.md); cosign signatures and a protected release environment needing the maintainer's approval (M2); tags never deleted. The Supervisor does not verify signatures, so verification is documented for users | Dry run implemented; publishing controls M2 |
| T68 | B13 | S | **A look-alike repository** (same name, different owner) offered through a copied link | The documentation's My links carry the exact owner and repository; a test checks them against `project.yaml`; the integration's discovery check accepts only MeshBeacon slugs and asks the user to confirm one from another repository (T35) | Implemented |
| T72 | B12 | E/T/I | **The discovery relay and the discovery credential**, misused or read by the core or by another process in the container, in particular by the Reticulum child, which handles untrusted network traffic and runs as the same user as the core | **Relay:** root-only socket (0600 in a 0700 root folder) and a peer check: only root may connect. The core never connects itself: its root start step (`relay_link.py`) opens the one link and hands it over. **Supervisor token:** in socket mode it is not passed at all; on the compatibility path the root start step passes it through a **one-time pipe** that the core reads once and closes, so it is in **no process environment**. **Core process:** non-dumpable (`PR_SET_DUMPABLE 0`) before it reads any credential or starts any child, so the kernel refuses other non-root processes, including Reticulum, access to the core's `/proc` environment, descriptors, memory map and memory, and ptrace (precisely: every non-root process without `CAP_SYS_PTRACE`, which is what Reticulum is; root in the container keeps some read access to `/proc/<pid>/environ` and `maps` even without that capability, but root already controls the container); descriptors are non-inheritable and children start with `close_fds`. **Container environment:** s6-overlay keeps a copy of the container's environment, the Supervisor token included, in `/run/s6/container_environment`, readable by every user by default; the root init step makes it root's alone (0700/0600), and the probes check it (M4 WP1; found by the isolation probe). **Result, in both transports:** Reticulum can neither announce nor withdraw, and cannot recover the token. Relay hardening: two fixed operations, rebuilt from validated fields; 8 KiB per request; unfinished requests dropped after 5 s; at most 4 connections served together; the run-time folder created without following links and refused if unexpected; no content logged. **ptrace read vs trace:** MeshBeacon's AppArmor profile denies ptrace *trace* (attach, memory, descriptor copying) but not *read*: in CI, under enforcement, a same-user process could read another's `/proc/<pid>/environ` and descriptor list. The non-dumpable core is therefore the control MeshBeacon owns; AppArmor, Docker's seccomp profile and Yama are further layers whose effect on Home Assistant OS is confirmed only by SO-1. In CI the profile also refused `CAP_SYS_PTRACE` to a privileged process inside the container, so even an administrator's `docker exec --privileged` cannot inspect the core there (observed). **Corrections (M1.2):** the M1 relay accepted any process of the `meshbeacon` user; the first M1.2 change closed that only in socket mode, because on the compatibility path the token stayed readable in the core's initial environment through `/proc` (shown in a container test against the previous image). Both were corrected before any release. **Residual:** the core and Reticulum share a Unix user, so isolation rests on the kernel's dumpable and ptrace rules; separate users are a mandatory gate before M4 or any community service (roadmap, isolation gate IS-1 to IS-4) | Implemented (tests: `test_discovery_relay.py`, `test_token_handoff.py`, `test_discovery_socket.py`, container `assert_isolated` in both transports) |
| T73 | B2/B12 | I | **Discovery hand-over on today's Supervisors** crosses the internal network in plain HTTP (see T28, RR-9a) | Newer Supervisors: the per-app socket through the relay; the Supervisor token is not passed to the core at all, and a missing relay link never falls back to the internal network. Older ones (every released Supervisor today): the compatibility path, documented in the app's own documentation; no write-capable credential is ever sent this way. **The one-time pipe (T72) protects the token inside the container only; it does nothing for the network transport:** the token, the status token and the fingerprint still travel in plain HTTP to `http://supervisor`, where an app able to observe the bridge could capture them (residual RR-9a). Interception not demonstrated; lab test W3-4 (results kept private) | Partly mitigated |
| T74 | B2 | I | **A credential in a discovery message is persisted by Home Assistant** (config entries are in `.storage` and in backups) | Config entry v2 keeps only allow-listed keys (`ENTRY_KEYS`); extra fields are dropped on set-up, rediscovery and migration; tested, including against a real Home Assistant 2026.11.2 | Implemented |

### 4.1 v0.3 messaging: proposed threats (status: proposed, awaiting independent review)

New boundaries: **B9** remote LXMF senders → messaging process → HA automations; **B10** HA →
app messaging API (the first write path, [ADR 0010](../adr/0010-home-assistant-messaging-interface.md)).
Design: [v0.3 messaging](../research/v0.3-messaging.md).

| ID | Boundary | STRIDE | Threat | Proposed control | Acceptance |
|---|---|---|---|---|---|
| T43 | B9 | E/T | **Message content used as a command** by an automation (remote control by the back door) | Content delivered as untrusted text; no command helper; blueprint never acts on content; docs say match on contact only; commands remain v0.6 | MS-11 |
| T44 | B9 | S | **Spoofed sender** | Accept only `signature_validated` messages from contacts; hold `SOURCE_UNKNOWN` ≤ 10 min, then drop and count | MS-8 |
| T45 | B9 | D | **Spam and floods** exhaust CPU, disk or HA | Contacts-only by default; stamps in "anyone" mode; tickets for contacts; per-sender and global rate limits; size cap; bounded stores | MS-9, MS-10 |
| T46 | B9 | T/E | **Malicious payloads** (oversized fields, attachments, crafted UTF-8) exploit parsing in the app, the integration or the panel | Only title and content read, length-capped, validated UTF-8; other fields ignored; panel writes text only (T38) | MS-10, MS-20 |
| T47 | B10 | E | **The send path is abused** to message arbitrary addresses | Recipients are contact IDs from the app's allow-list only; raw addresses refused | MS-12 |
| T48 | B10 | S | **Another app uses the messaging API** | Separate 256-bit messaging key, per start, only in discovery (as T28); pinned TLS (T34) | MS-12 |
| T49 | B10 | D | **HA or an automation loop floods sends** (airtime, stamp CPU) | 10 a minute, 100 a day, per-contact limits; stamp CPU budget | MS-13 |
| T50 | B10 | T | **Duplicate sends** after timeouts and retries | Idempotency keys (24 h) | MS-5 |
| T51 | B10 | I | **Status key gains messaging access** | Keys scoped separately; tests that the status key gets 401 on messaging endpoints | MS-12 |
| T52 | B10 | D | **Long poll starves the status API** | ≤ 1 long poll; one connection slot reserved for status | MS-13 |
| T53 | — | I | **Message content in HA's recorder, logs, diagnostics or bus history** | Unrecorded attributes; no bus event with content; never logged; diagnostics counts only | MS-7 |
| T54 | — | I | **Content via mobile push relays** (Apple/Google) | Blueprint omits content by default and explains why | MS-7 |
| T55 | B5 | I | **Plaintext messages at rest** in `/data/messaging/queue.db` and in app backups | Acknowledged content deleted by default; bounded retention; documented; encrypted backups recommended | MS-4 |
| T56 | B5 | I/T | **Messaging identity theft or silent replacement** | 0600, validated before start (rule 13), never logged, separate from transport identity ([ADR 0009](../adr/0009-messaging-identity.md)) | MS-2 |
| T57 | B1 | I | **Metadata disclosure**: recipient hash, size and timing to propagation nodes; announce correlation with the transport identity; display name | Empty display name by default; no telemetry, location or icon fields; documented limits of separation | MS-3 |
| T66 | B10 | I/T/E | **A new binding weakens messaging protection** (for example a delivery added for convenience whose channel lacks confidentiality, integrity or caller authentication) | Every binding must meet S1–S3 before it may carry content or accept a send; read-only is not an exception; bindings are thin and reviewed (ADR 0014) | MS-22 |
| T58 | B5 | D | **Messaging failure disturbs transport** (crash, hang, stamp CPU, corrupt queue, full disk) | Separate process ([ADR 0008](../adr/0008-messaging-process.md)), bounded restarts, `nice`, CPU limit for stamps, quarantine of a corrupt queue | MS-15, MS-16 |

### 4.1a M4 messaging engine, as implemented (standard image, off by default)

Since D-M4-8 ([ADR 0022](../adr/0022-standard-image-optional-messaging.md)) the engine is in the one
standard image and runs only when the user switches messaging on; until then it was in the
`messaging-dev` target only. Evidence: [M4 results](../testing/m4-results.md). Changes to the
proposed controls above are marked.

| ID | Boundary | STRIDE | Threat | Control | Status |
|---|---|---|---|---|---|
| T75 | B12 | S/T/D | **Another process uses the RNS shared instance** (IS-3a): in RNS 1.6.0 it is an abstract Unix socket with no peer check | It lives in the app container's own network namespace (no host network), so other containers and apps cannot reach it. The RPC listener needs a key that only Reticulum's user and the engine's user can read (ADR 0023, proposed: `root:mb-rpc 0640`, new at every container start); the core and anyone else are refused. Reticulum shares its instance only while messaging is switched on (off by default). **Residual:** any process inside the container can send packets through it | Implemented (container tests) |
| T76 | B9 | R/I | **A delivery state is read as more than it is** (for example "delivered" as "read", or "stored on node" as "delivered") | Each state documents what it does and does not establish (`contract.STATE_MEANINGS`). LXMF proves delivery before the recipient's policy runs: the MS-9 test shows a sender told "delivered" for a message the engine refused | Implemented |
| T77 | — | E | ~~The engine reaches a production image by mistake~~ **Superseded by D-M4-8:** the engine is in every image. **New threat: it runs, or its data is created, while messaging is off** | The service ships with a `down` file and the core starts it only when the validated option is on; the root init step creates no messaging folder or data while it is off; Reticulum shares its instance only while it is on. Container tests check all of it with the option off, on and toggled; release verification requires the `down` file | Implemented |
| T78 | B12 | I/T | **The engine reads secrets meant for others, or changes its own settings** (D-M4-8: its settings now come from the app's options, which hold peer passphrases) | The engine never reads `options.json`; the core writes only the engine's settings to a folder it owns (group `mb-msg`, 0750; file 0640), which the engine reads but cannot change and Reticulum's user cannot reach; the engine's own parser validates them again. Tested in the container | Implemented |
| T79 | B9 | I | **The messaging address or message content reaches Home Assistant's history, logs or diagnostics** | Since M5 the core forwards content only between the engine and the administrator's open panel and keeps none; the integration creates no entity or bus event from it and never logs it (tested); conversations live only in the engine's `queue.db`; the address is an attribute excluded from the recorder, and diagnostics redact it and contact names; addresses never reach the app log (redaction) | Implemented (unit and HA tests) |
| T80 | B2/B9 | S/E | **Someone other than an administrator reads or sends messages** (M5) | Every `meshbeacon/messaging/*` websocket command requires an HA administrator; the app's messaging endpoint takes only the separate messaging key (never the status key); the key is never sent to the browser. Tests: `tests/ha/test_messaging.py`, `tests/unit/test_api.py` | Implemented |
| T81 | B2 | I/T | **The messaging key is captured on the compatibility path** (RR-9b, ADR 0024 D-M5-1): it travels with the status key in the plain-HTTP discovery message on Supervisors without app sockets | Approved trade-off: a new key at every app start; sent only while messaging and the HA integration are both on; never with plain HTTP to the app (TLS fingerprint required); held in memory only in HA. The same attacker can already capture HA Core's Supervisor token. Gone on Supervisors with app sockets | Accepted (RR-9b) |
| T82 | B9 | T/I | **Message text injects markup or script into the panel** | Text is set only as `textContent` (dom.js), never parsed; tests forbid `innerHTML` and friends in every frontend file; the preview's `&hostile=1` shows markup as text | Implemented |
| T83 | B9/B10 | D/T | **Home Assistant floods the engine or sends duplicates** (double clicks, retries, a script) | The core forwards only the view's operations; sends 10 a minute and 200 a day; 4 messaging requests at once, so status keeps a slot; every Send carries an idempotency key; long polls ≤ 8 s; the engine validates again. Automatic replies at most once per contact every six hours (no loops) | Implemented |
| T80 | B12 | T/D | **The engine misuses the node's RPC** (ADR 0023, proposed): with the shared key a compromised engine could drop the node's paths and announce queues, or blackhole identities | The key is readable by Reticulum's and the engine's users only, never the core; interface management over RPC is off while the instance is shared; the key gives no access to Reticulum's files, identity or configuration; messaging is off by default. **Residual:** degraded routing until the next restart, or blackholed identities until unblackholed | Proposed (container tests) |
| T44 (change) | B9 | S | Spoofed sender | As proposed, except that `SOURCE_UNKNOWN` messages are held for **2 minutes** (at most 50) while the sender's key is requested, then re-verified with LXMF's public `unpack_from_bytes` or dropped and counted. Contacts' keys are requested at start and every 30 minutes | Implemented |
| T45 (change) | B9 | D | Spam and floods | As proposed; tickets are given only to contacts, in "anyone" mode | Implemented (MS-9 negative and positive) |
| T58 (change) | B5 | D | Messaging failure disturbs transport | As proposed, with health checks over the socket and a pause after five failures in 30 minutes | Implemented (MS-15) |

## 5. Privacy commitments

- No telemetry, analytics, crash reporting or "phone home" of any kind.
- No outbound connection that the user has not configured (apart from the Supervisor pulling
  images).
- Status messages and diagnostics contain no identity hashes, passphrases or tokens; peer
  hostnames appear in the app log (which the user controls) but are redacted from any future
  shareable diagnostics file.

## 6. Vulnerability reporting

Private vulnerability reporting through GitHub must be **enabled** on the repository by the
maintainer (Settings → Code security → Private vulnerability reporting). Its current state could
not be checked from the research environment — see [SECURITY.md](../../SECURITY.md) and
feasibility Q-27.

## 7. Review

Revisit this model at every minor version, whenever a permission or default changes, and before
the v1.0 external security audit.

## App dashboard amendment (21 Nov 2026, ADR 0026)

Ingress is now accepted by the maintainer. The internal Supervisor-to-app hop is plain HTTP;
network interception remains an accepted limitation. The app trusts only the actual Supervisor
peer, uses no forwarded IP for authentication, and relies on Supervisor's admin-only Ingress
access. POST requires JSON plus a non-simple request header; no CORS permission is emitted.
Static paths are allow-listed and content-versioned. Requests, concurrency and time are bounded.
Management admits only validated self-options, self-restart and first-run sidebar enablement.
No arbitrary proxy, identity replacement, broader Supervisor role, external port or host mount is
introduced. Optional integration TLS and existing process/user separation remain in place.

## Nomad Network pages (v0.6.0, ADR 0027; implemented on the feature branch, awaiting review)

New assets: the page host's identity (`/data/nomadnet/nomadnet/storage/identity`, `mb-nomad`
0600), the user's drafts and published pages (`/data/pages`, the core's), bookmarks and heard
nodes. New boundary B13: other Reticulum users ↔ the pages service and the Nomad Network daemon.

| ID | Boundary | STRIDE | Threat | Control | Status |
|---|---|---|---|---|---|
| T84 | B13 → browser | T/E | **A remote page carries script, HTML or a hostile link** to run code in the Home Assistant session or reach its API | Pages are parsed into data (`micron.js`) and built with `textContent` only; no HTML, styles, colours, images or forms; only `/page/*.mu` Nomad links are followed, inside the viewer; the dashboard's CSP (`script-src 'self'`) stays; no browser storage. Tested with hostile content in Chromium (`tools/pages_browser_check.py`) and in unit tests | Implemented |
| T85 | B13 → service | D | **Oversized, slow or malformed answers; many requests** | Address and path allow-lists (no `..`, no other request types); 30 s per fetch; 256 KiB answers; 2 fetches at once and 30 a minute in the service, 30 a minute in the core; at most 4 links, closed after 2 min idle; untrusted bytes decoded with replacement and stripped of control characters | Implemented |
| T86 | B13 → daemon | D | **Strangers fill the page host's LXMF inbox or storage** (anyone who sees its announce can message its identity, F4) | Stamp cost 16, 1 KB per message, its own address never announced, no propagation; storage checked every 5 min, hosting stops above 64 MiB; backups exclude its cache | Implemented (residual: up to 64 MiB of unread messages) |
| T87 | B9 | E | **The daemon runs a page as a script** (it executes any page file with the execute bit, F6) | Pages are the core's files, 0640, never executable; the daemon's user cannot write to `public/`; AppArmor forbids execution from `/data` | Implemented (container test) |
| T88 | B12 | T/D | **The daemon becomes the shared instance** while Reticulum is down (it does not require one, F5), so that ito's node runs as its client | The core runs the service only while Reticulum is up and stops it when Reticulum stops; the service starts the daemon only while connected; the node now exits if another program holds the instance, so the core restarts in order | Implemented |
| T89 | B12 | E | **The pages service misuses the node's RPC** (it holds the shared key, ADR 0023) | As T80: interface management off; pages off by default; separate user `mb-nomad` | Accepted (as T80) |
| T90 | B9 | I | **Drafts or other services' data leak to the network** | Drafts are the core's alone (0700/0600); only `public/` is the daemon's `pages_path`; `mb-nomad` cannot read Reticulum's, messaging's or the core's folders or `options.json` (container test); the node address is shown in the dashboard only, never in the status API or logs | Implemented |
| T91 | B13 | S | **A page or announce impersonates a known node by name** | Names are shown as untrusted text beside the address; navigation is by address; "reachable" only after a successful fetch | Accepted (inherent to announces) |
| T92 | Supply chain | T | **A compromised `nomadnet`, `urwid` or `wcwidth` release** | Hash-pinned wheels from PyPI, binary-only, no dependencies resolved at build time; releases public for some weeks preferred; GPL program run separately under its own user | Implemented |
