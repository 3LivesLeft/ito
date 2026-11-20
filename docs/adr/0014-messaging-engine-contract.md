# ADR 0014: The messaging engine is independent of any frontend or delivery

- **Status:** **Proposed — awaiting independent review.** Not to be implemented until reviewed and
  approved by the maintainer.
- **Date:** 18 November 2026
- **Driver:** the maintainer's requirement that the messaging engine must not depend on a
  particular frontend delivery mechanism, and that development must not depend on upstream
  Home Assistant security changes.
- **Evidence:** [v0.3 messaging](../research/v0.3-messaging.md),
  [architecture §6a](../architecture.md) (interface layers),
  [secure interface options](../research/secure-interface-options.md)

## Context

LXMF messages must eventually be sent and received from MeshBeacon's built-in interface, which
does not yet exist securely (ADR 0013 blocked). Until then, messaging reaches users through the
Home Assistant integration (ADR 0010). If the engine were shaped around either path, the other
would need rework.

## Decision

1. **One engine, one contract.** The messaging process (ADR 0008) owns everything about
   messaging: the identity (ADR 0009), contacts, the queue and receipts (ADR 0011), the LXMF
   router and the optional propagation node (ADR 0012). It exposes a versioned, transport-neutral
   **Messaging Service contract v1**:

   | Operation | Input | Output |
   |---|---|---|
   | `send` | contact ID, text, optional title, idempotency key | message ID |
   | `message` | message ID | state, reason, times |
   | `inbound` | cursor, wait (≤ 25 s) | messages after the cursor |
   | `ack` | cursor | — |
   | `contacts` | — | contact IDs and display names (no addresses) |
   | `status` | — | engine state, queue sizes, propagation-node reachability (counts only) |

   | Event | Payload |
   |---|---|
   | `message_received` | message ID, contact ID, time, title, content |
   | `message_status` | message ID, new state, reason |

   States and limits are as in ADR 0011. The contract has no Home Assistant concepts (entities,
   notify, users) and no presentation concepts.

2. **Bindings are separate, thin and replaceable.** A binding carries the contract over one
   channel and adds that channel's authentication. It holds no messaging logic.

   | Binding | Channel | Status |
   |---|---|---|
   | Engine ↔ core | Local pipe inside the container (the same pattern as the status line) | v0.3 |
   | Core ↔ Home Assistant | The existing pinned-TLS listener with the scoped messaging key (ADR 0010) | v0.3 |
   | Home Assistant ↔ browser | The integration's authenticated HA websocket commands, used by the panel's Messages view | v0.3 |
   | Built-in interface | Any delivery that meets requirements S1–S3 (secure interface options §3) | Later; **no engine change** |

3. **Presentation follows the interface layers.** A **conversation view-data contract** (contacts,
   conversations, message states) sits beside the status contract in `model.js`. Messages views
   are written once in `ui/`. Each delivery supplies a data source (`sources/hass.js` through the
   integration today; a built-in source later).

4. **Every binding must protect the user's data.** No binding may carry message content or accept
   a send unless its channel provides confidentiality, integrity and caller authentication
   (S1–S3). A read-only binding is not an exception.

## Consequences

- Messaging can ship in v0.3 through the integration without waiting for upstream Home Assistant
  changes. A secure built-in delivery adds a binding and a data source, with no engine or view
  rework.
- The contract becomes the unit of testing. Contract tests run the real engine (isolated LXMF on
  loopback) behind a fake binding. Each binding has its own authentication and limit tests.
- One more versioned interface to maintain, as for the status snapshot (schema 1).
- Architecture tests enforce the boundary. The engine imports no Home Assistant, HTTP-server or
  UI code. Bindings import no LXMF. Views use only the contracts.

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| Build messaging into the integration (HA owns the queue) | Messaging would depend on Home Assistant running, and a built-in interface would need a second implementation |
| Build messaging around the built-in interface first | Blocked on an upstream security change, which the maintainer has ruled out as a dependency |
| One endpoint per feature, not a contract | Each delivery would grow its own semantics; receipts and idempotency would drift |
