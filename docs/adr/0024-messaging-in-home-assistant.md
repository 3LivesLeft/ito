# ADR 0024: Two-way LXMF messaging in Home Assistant (M5)

- **Status:** **Accepted** (maintainer, 20 Nov 2026: implementation of M5 requested; the
  compatibility-path delivery of the messaging key approved explicitly, decision D-M5-1 below).
- **Date:** 20 November 2026
- **Implements:** [ADR 0010](0010-home-assistant-messaging-interface.md) (option A, with the
  changes listed here), within the contract of [ADR 0014](0014-messaging-engine-contract.md).
- **Amends:** [ADR 0006](0006-local-metrics-api.md) ("rule carried forward": no write credential on
  the compatibility path), MS-4, MS-12 and MS-20 in the [roadmap](../roadmap.md).

## Context

M4 runs the LXMF engine (separate user `mb-lxmf`, ADR 0018) and answers contacts automatically,
but nothing in Home Assistant can read or send messages. M5 adds a Messages view to the existing
sidebar panel (ADR 0007): conversations, contacts, sending and accurate delivery states, with live
updates and history that survives restarts.

## Decision

### Path and who checks what

| Hop | Transport | Authentication and authorisation | Limits |
|---|---|---|---|
| Browser → HA | HA websocket, `meshbeacon/messaging/*` | HA login; **administrators only** (`require_admin`), like the panel | Inputs validated (contact IDs, 8 KiB text, idempotency key) before anything leaves HA |
| HA → app core | `POST /api/v1/messaging` on the existing pinned-TLS listener | A **separate messaging key** (256-bit, per app start). The status key is refused there and the messaging key is refused for status | 64 KiB bodies (8 KiB of text however JSON escapes it); at most 4 messaging requests at once (listener 4 → 6, so status always has a slot); sends 10/min and 200/day; other requests 240/min; long poll ≤ 8 s |
| Core → engine | Unix socket (`SO_PEERCRED` both ways, ADR 0014) | Only the core's user; the core forwards an **allow-list** of the view's operations and never `auto` | The engine validates everything again |

The browser never holds a key. The messaging key exists only while **Enable LXMF messaging** and
**Show MeshBeacon's status in Home Assistant** are both on: no separate "allow Home Assistant to
send" option (ADR 0010 proposed one), because the user's own two switches already express that
intent and a third would cost the five-minute set-up (vision principle 2).

### The key in Home Assistant: memory only

The key arrives in the app's discovery message. The config flow and the coordinator keep it in
`hass.data` only, never in the config entry (`ENTRY_KEYS` is unchanged), so it is not in
`.storage`, backups or diagnostics. After a restart of HA it is read again from the Supervisor's
discovery store (only HA Core can read that), and again after a 401.

### D-M5-1: the key on the compatibility path (approved trade-off)

On Supervisors without per-app sockets (every stable release at the time of writing, including
the reference Pi), the discovery message crosses HA's internal network in plain HTTP (RR-9a). The
messaging key now travels in it. **Residual risk RR-9b:** another app with `NET_RAW` that ARP-spoofs
on that network could capture the key and read or send messages until the next app start. That
attacker could already capture HA Core's own Supervisor token on the same network, which is far
more powerful. The maintainer approved delivery on both transports (20 Nov 2026). On Supervisors
with app sockets, the key never crosses the network.

### One authoritative contact store

`contacts` in the engine's `queue.db` (owned by `mb-lxmf`, 0600). Contacts from the app's options
are imported at each start, by address; the dashboard adds, renames and removes. A rename in the
dashboard wins over the options; a contact removed in the dashboard is not imported again while
it stays in the options; one taken out of the options is kept (no silent loss of a conversation).
Inbound policy reads this store, so adding a contact admits it at once and removing it refuses it
at once. **Signature verification, the "contacts only" default and stamps are unchanged.**

### Conversation history

`history` in the same file: both directions, in arrival order, de-duplicated by LXMF message hash,
at most 10,000 messages and 8 MiB of text (oldest first), never pruning a message still to be sent.
MS-4 changes: acknowledged inbound content is still deleted from the delivery queue at once, but
the conversation keeps it until the user deletes the conversation or the contact, or the limits
prune it. History lives with the engine; the core and HA never store it. While messaging is off
the engine does not run (MS-1), so conversations are **kept but not shown** until it is on again.

### Addresses in the contract (MS-12)

Sends still name a contact ID only; a raw address is never a recipient. A contact's address now
crosses the contract in `contact_add` (typed by the user) and `conversations` (shown, to check and
copy). The core's status API and HA entities still carry no contact address.

### Delivery states

Unchanged from ADR 0011: the view says *Delivered* only for LXMF's delivery proof;
*Stored on a propagation node* is never shown as delivered. Undelivered messages
(`failed`, `rejected`, `expired`, `sent_unconfirmed`) can be sent again: a new message with the
same text takes the old one's place. A Send carries an idempotency key made once per press, so a
double click or a retried request is one message.

### Live updates

The engine raises a revision on every change the view shows; `wait` (long poll) returns as soon
as it changes. While at least one panel is subscribed and visible, the integration holds one such
poll per app (8 s, at most one a second) and pushes `{"type": "changed"}` or
`{"type": "unavailable"}`, never content; the panel then reads what it shows. Nobody watching: no
requests.

Amended (21 Nov 2026, reconnection-storm fix): only a command that **changes** something (send,
retry, read, clear, contact add, rename, remove) is announced as `changed`; a read
(`conversations`, `history`) never is, because the panel answers every announcement with reads.
Announcing reads made an endless conversations/history loop as soon as a conversation was open,
which used up the 240 reads a minute in about a second and left the view on "Reconnecting". As
defence in depth the panel reads after announcements at most once every 2 s, and after a failed
read waits with a bounded, jittered back-off (2 s up to 60 s; from 15 s when refused for asking
too often) with one retry timer at most, cancelled when the view is hidden. The app's single
`rate_limited` code is passed to the panel as `busy` for reads (sending has its own allowance and
stays possible), and only outages (`unavailable`, `unreachable`, `not_enabled`, `unauthorised`)
show as "Reconnecting". Refusals are logged by the app and by the integration at most once a
minute per kind, with counts only (never content, contacts or keys).

### Automatic replies

Kept and configurable. At most one per contact every six hours (no loops between two automatic
responders), sent with `auto` (only the core may set it) and shown as "Automatic reply".

## Consequences

- MeshBeacon is no longer read-only towards Home Assistant: administrators can send messages to
  contacts and edit contacts. Nothing else is controllable.
- New tests: engine store and contract (`test_messaging_conversations.py`), real LXMF two-way with
  a contact added from the dashboard and restart (`test_messaging_lxmf.py`), core binding and API
  (`test_messaging_binding.py`, `test_api.py`), relay allow-list, HA path (`tests/ha/test_messaging.py`),
  panel source (`tests/frontend/messages.test.mjs`).
- Threat model: RR-9b, T80–T83.

## Review triggers

Multi-user access (non-admin users), attachments, any operation beyond the view's allow-list, a
Supervisor release with app sockets (re-check that the TCP path is no longer used).
