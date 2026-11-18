# ADR 0006: Read-only local status API, delivered to Home Assistant by Supervisor discovery

- **Status:** Proposed. Needs maintainer approval. Under CLAUDE.md rule 4, the new listener and
  the use of discovery need an approved ADR, so the option ships **off** until then.
- **Date:** 18 November 2026
- **Evidence:** [v0.2 feasibility and architecture](../research/v0.2-observability.md),
  [threat model T11, T28–T33](../security/threat-model.md)

## Context

v0.2 must show the node's health, peers, traffic and resource use in Home Assistant, with HA's own
history and statistics, without new privileges, telemetry or public endpoints. The app has no
access to Home Assistant's API (by design), so Home Assistant must fetch the data. The fetch must
be authenticated, because every app on the Supervisor's internal network can reach every other app.

## Decision

1. The core serves **one read-only endpoint**, `GET /api/v1/status` (versioned schema 1), on a
   **separate internal port, 8100**, only when the new option `home_assistant_integration` is on.
   It has no write or control endpoints and publishes no port.
2. Access needs a **bearer token of 256 random bits**. It is created in memory at every core start,
   compared in constant time, never written to `/data` and never logged.
3. The token reaches Home Assistant **only through Supervisor discovery**
   (`discovery: [meshbeacon]`). Apps may post discovery without `hassio_api`, and only Home
   Assistant Core can read messages (verified, Supervisor `e610ca8`). The security rating is
   unchanged.
4. The **Supervisor token** is used only to post or withdraw that message. It is removed from the
   environment of the prepare step and of Reticulum.
5. The server is **bounded**: at most 4 concurrent requests (others are closed), a 5 s socket
   timeout and a pre-built snapshot. The watchdog's `/health` stays on its own port and server.
6. A **custom integration** (`custom_components/meshbeacon`) consumes the API. It is set up only
   through discovery, polls every 30 s, never imports Reticulum or the core, and keeps no history
   of its own: Home Assistant's recorder does. A dashboard of native cards is supplied instead of a
   second UI.

## Alternatives rejected

App-side `homeassistant_api` (gives the app write access to Home Assistant); MQTT (extra broker,
credentials, and topics readable by other clients); an unauthenticated API (readable by every
app); an Ingress UI (a second monitoring implementation). See
[feasibility §2](../research/v0.2-observability.md#2-options-considered-for-home-assistant).

## Consequences

- One new internal listener while the option is on; none while it is off (v0.1 behaviour).
- About 2 MiB more idle memory (71.3 MiB against 69.2 MiB, amd64, stand-in base).
- Each app restart rotates the token; the integration's entities are unavailable for a few seconds
  until Home Assistant processes the new discovery message.
- HA stores the token in its config entry and therefore in HA backups. It grants read-only access
  to non-identifying metrics and changes at the next app start.

## Review triggers

Any request to add a write endpoint, publish the port, or expose identifiers; an RNS version that
changes the counters read (the contract test fails); a change in the Supervisor's discovery
permissions.
