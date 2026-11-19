# ADR 0006: Read-only local status API, delivered to Home Assistant by Supervisor discovery

- **Status:** **Accepted**; amended 19 Nov 2026 (discovery transport, below).
- **Original status:** **Accepted** (maintainer, 18 November 2026, after a positive independent review of
  PR #3 with all 14 CI checks confirmed passing). The `home_assistant_integration` option stays
  **off by default, permanently**. That is a decision, not a placeholder until approval.
  Follow-up after acceptance: the client's response reading was made complete and bounded (threat
  model T37).
- **Date:** 18 November 2026; revised after independent review the same day
- **Evidence:** [v0.2 feasibility, architecture and security review](../research/v0.2-observability.md),
  [threat model T11, T28–T36](../security/threat-model.md),
  [v0.2 results](../testing/phase2-results.md)

## Context

v0.2 must show the node's health, peers, traffic and resource use in Home Assistant, with HA's own
history and statistics, without new privileges, telemetry or public endpoints. The app has no
access to Home Assistant's API (by design), so Home Assistant must fetch the data.

That traffic crosses the Supervisor's internal Docker network, shared by every app. The fetch must
therefore be authenticated, and, as the review established, also encrypted. The Supervisor leaves
`NET_RAW` to apps unless an opt-in feature flag is set, which allows ARP spoofing on that network
(verified, below).

## Decision

1. The core serves **one read-only endpoint**, `GET /api/v1/status` (versioned schema 1), on a
   **separate internal port, 8100**. It is served only when `home_assistant_integration` is on
   (default off). There are no write or control endpoints, and no port is published.
2. **HTTPS only, TLS 1.3, with a throwaway certificate made at every start.** It is generated in a
   short-lived process; the key is on disk only while it is loaded. Home Assistant does not trust
   it through any authority: it **pins its SHA-256 fingerprint**. There is no fallback to plain HTTP.
3. Access needs a **bearer token of 256 random bits**. It is created in memory at every start,
   compared in constant time, never written to `/data` and never logged.
4. The token and the fingerprint reach Home Assistant **only through Supervisor discovery**
   (`discovery: [meshbeacon]`).
   - Apps may post discovery without `hassio_api`; only Home Assistant Core can read the messages.
   - The Supervisor attaches the sending app's slug from that app's own credentials.
   - The security rating is unchanged.
5. **Discovery is checked against spoofing:**
   - the slug must be a MeshBeacon slug (`local_meshbeacon` or `<repository hash>_meshbeacon`);
   - the host must be *that app's own* internal hostname;
   - a fingerprint is required.
6. **Discovery recovers by itself.** It retries with capped back-off and refreshes the message every
   6 h. If Home Assistant misses a key-rotation push, the integration reads its own app's message
   from the Supervisor, matched by slug.
7. The **Supervisor token** is used only for discovery. It is removed from the environment of the
   prepare step and of Reticulum.
8. **Bounded servers**, each with an inactivity timeout *and* an absolute per-connection deadline:

   | Server | Concurrent connections | Deadline |
   |---|---|---|
   | API (port 8100) | 4 | 10 s |
   | Watchdog `/health` (port 8099, separate server) | 16 | 5 s |

   Connection errors are counted, never printed. Monitoring failures are isolated from the loop that
   supervises Reticulum.
9. A **custom integration** (`custom_components/meshbeacon`) consumes the API.
   - It is set up only through discovery and polls every **60 s**.
   - It never imports Reticulum or the core.
   - It keeps no history: Home Assistant's recorder does.
   - High-churn detail is disabled by default. A dashboard of native cards replaces a second UI.

## Alternatives rejected

App-side `homeassistant_api` (gives the app write access to Home Assistant); MQTT (extra broker,
credentials, and topics readable by other clients); an unauthenticated API (readable by every
app); an Ingress UI (a second monitoring implementation). See
[feasibility §2](../research/v0.2-observability.md#2-options-considered-for-home-assistant).

## Review outcome (18 November 2026)

| Review item | Finding | Disposition |
|---|---|---|
| Unencrypted internal HTTP | **[Verified]** Apps keep `NET_RAW` unless the Supervisor's `app_drop_net_raw` feature flag is on (default off; Supervisor `e610ca8`, `docker/app.py` `dropped_capabilities`, `config.py` `feature_flags`), so another app could ARP-spoof and read the token and the data, or impersonate MeshBeacon | **Fixed:** pinned HTTPS (decision 2) |
| Token leaks through diagnostics, logs, exceptions, exports | None found. Tested under every failure mode | Covered by tests; storage at rest documented (feasibility §8) |
| Discovery spoofing | An app that declares the `meshbeacon` service could post discovery and, unchecked, point the integration at any host | **Fixed:** slug, host and fingerprint checks (decision 5); a look-alike from another repository needs the user's confirmation, which names the app and slug |
| Absolute request deadline | Needed: a client trickling one byte within each timeout could hold a slot indefinitely | **Fixed:** per-connection deadline on both servers (decision 8) |
| Floods and slow clients | 30 s of hostile traffic on both ports: watchdog answered 30/30; Reticulum not restarted and stayed connected; core threads ≤ 36; core memory +2 MiB | Tested (`test_sustained_flood_and_slow_clients`) |
| Monitoring failure interrupts Reticulum | **Defect found:** an exception in the collector's update stopped the supervisor loop | **Fixed:** every metrics call isolated; tested |
| Discovery failure needs a restart | Earlier: three attempts, then nothing | **Fixed:** retries for ever and refreshes (decision 6); tested with the Supervisor failing, down at start and restarting |
| Recorder load | 30 s polls with everything on: about 15 rows per poll, about 8 MB a day with one peer and more with each peer | **Reduced:** 60 s polls, churn off by default, rounding; about 6 rows per poll, about 1.9 MB a day worst case, roughly independent of peers |

## Consequences

- One internal listener while the option is on; none while it is off (v0.1 behaviour).
- Idle memory 70.8 MiB on, against 67.8 MiB off (amd64, stand-in base; Pi pending).
- Each app restart rotates the token and the certificate. The entities are unavailable until Home
  Assistant receives the new discovery message, normally seconds; if the push is missed, within 5
  minutes.
- Residual risks are listed in [feasibility §8](../research/v0.2-observability.md#8-residual-risks).
  The main one: anything that can read Home Assistant's configuration (admins, apps mapping
  `/config`, HA backups) can read the current token until the next app restart. It grants read-only
  access to non-identifying metrics.

## Amendment (19 November 2026, M1): how discovery reaches the Supervisor

Decision 4 says the token and fingerprint reach Home Assistant only through Supervisor discovery.
That remains true of *reading* them, but the delivery path needs a precise statement:

| | Status |
|---|---|
| On Supervisor 2026.11.0 and older, the app posts its discovery message to `http://supervisor` over the internal network in plain HTTP, with its Supervisor token | **Confirmed** from source |
| Apps keep `NET_RAW` unless the Supervisor's opt-in `app_drop_net_raw` flag is set | **Confirmed** from source |
| A co-installed app can intercept or alter that message on Home Assistant OS | **Not verified.** The same class as T34; not reproduced. A lab test is planned (W3-4) |
| Impact if it can | Read-only, non-identifying metrics until the next app start (residual RR-9a, threat T28) |

**Change (implemented in M1):** where the Supervisor gives the app its own Unix socket (newer
Supervisors), the app posts discovery through it, via a small root-owned relay
(`core/meshbeacon/discovery_relay.py`), because the socket is root-only and the core runs
unprivileged. The token is then not used at all. Older Supervisors keep the compatibility path
above. The relay adds no `config.yaml` privilege, sends only MeshBeacon's own validated message
and serves only the core.

**Rule carried forward:** no write-capable credential (for example a future messaging key) is ever
delivered over the compatibility path ([secure interface options](../research/secure-interface-options.md),
D7). Home Assistant keeps no field from a discovery message other than the status connection's
(config entry v2, `ENTRY_KEYS`).

## Later decisions (19 November 2026, roadmap reconciliation)

- [ADR 0021](0021-v0.3-scope.md) removes the HA `notify` platform from the committed v0.3 scope.
  v0.3.0 therefore adds no write path, and the status key stays read-only. Any sending path for
  the v0.3 messaging milestone needs its own approved ADR: [ADR 0010](0010-home-assistant-messaging-interface.md)
  is the proposal, and gates MG-1 and MG-2 apply.
- [ADR 0020](0020-public-service-isolation.md): public services never use this API or its
  credentials.

## Review triggers

Any request to add a write endpoint, publish the port, or expose identifiers; an RNS version that
changes the counters read (the contract test fails); a change in the Supervisor's discovery
permissions or in how it assigns hostnames or capabilities.
