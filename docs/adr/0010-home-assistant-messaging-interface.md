# ADR 0010: Home Assistant messaging interface (the first write path)

- **Status:** **Proposed — awaiting independent review.** Not to be implemented until reviewed and approved by the maintainer.
- **Date:** 18 November 2026
- **Evidence:** [v0.3 feasibility and architecture](../research/v0.3-messaging.md), [threat model T43–T58](../security/threat-model.md)
- **Note:** this ADR **changes the "read-only" property** of ADR 0006, so it needs explicit approval.

## Context

v0.2's integration only reads status. Messaging needs Home Assistant to **send** (a write) and to
**learn of inbound messages quickly** (push-like). The app has no Home Assistant API permission,
by design, and must not gain one.

## Options

| | **A. Pinned-TLS API, separate key, long poll** | B. App calls HA (`homeassistant_api`) | C. MQTT | D. Ingress UI |
|---|---|---|---|---|
| New app permission | **None** | Yes (lowers the rating) | None, but needs a broker | `ingress` (forbidden by posture) |
| New trust boundary | **Reuses B2 (pinned TLS)** | HA's API exposed to the app | Broker with its own accounts | Browser to app |
| Latency for inbound | **Seconds (long poll)** | Immediate | Immediate | — |
| Complexity | **Low** | Medium | Medium to high | High |

## Decision

**A.**
- A separate option, "Allow Home Assistant to send messages", **off by default**.
- A separate **messaging key** (256-bit, per start), delivered with the status key in the same
  discovery message only while messaging is on. The status key cannot send.
- Endpoints on the existing pinned listener: `POST /api/v1/messages` (contact ID, text, title,
  idempotency key) → `message_id`; `GET /api/v1/messages/{id}`;
  `GET /api/v1/messages/inbound?after=&wait=25` (long poll); `POST /api/v1/messages/inbound/ack`.
- **Recipients are contact IDs only.** Raw LXMF addresses from HA are refused.
- Limits: 10 sends a minute, 100 a day, 8 KiB content, at most 1 long-poll connection.
  Connection limit 4 → 5 (Q-44), with one slot reserved for status.
- Integration: `notify` entities per contact; `meshbeacon.send_message` with an action response;
  `event` entities for received messages and receipts; **content and title as unrecorded
  attributes**; a blueprint whose notification omits content by default.

## Consequences

- MeshBeacon is no longer strictly read-only. The README, the app description and ADR 0006's
  "read-only" statements must change when this is approved.
- The threat model gains B10 and T47–T52.
- No control beyond sending to known contacts. Anything more is v0.6, under its own review.
