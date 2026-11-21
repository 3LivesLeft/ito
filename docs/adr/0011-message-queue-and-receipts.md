# ADR 0011: Persistent, bounded message queue and receipts

- **Status:** **Proposed — awaiting independent review.** Not to be implemented until reviewed and approved by the maintainer.
- **Date:** 18 November 2026
- **Evidence:** [v0.3 feasibility and architecture](../research/v0.3-messaging.md), [threat model T43–T58](../security/threat-model.md)

## Context

**[Verified]** In LXMF 1.3.1 the router's outbound queue is held in memory, and in-flight messages
are lost at a restart. There is no automatic fall-back from direct to propagated delivery. Home
Assistant may be offline when messages arrive.

## Decision

1. Use `/data/messaging/queue.db` (SQLite from the standard library, WAL, `synchronous=NORMAL`)
   with two tables, `outbound` and `inbound`. All writes are transactional.
2. **Outbound states:** queued → sending → delivered | stored_on_node | sent_unconfirmed | failed
   | rejected | expired. On restart, queued and sending rows are resubmitted. One resubmission as
   `PROPAGATED` follows a direct failure, if a node is configured. Expiry is 7 days; pending rows
   are capped at 200.
3. Idempotency keys from HA are remembered for 24 h, so the same key returns the same
   `message_id`.
4. **Inbound:** stored until HA acknowledges it (at-least-once). The integration de-duplicates by
   `message_id` (effectively once). Caps: 500 messages and 2 MiB; when full, the oldest is dropped
   and counted. Acknowledged content is deleted at once (default) or kept for ≤ 30 days.
5. The file has a 16 MiB hard cap and a weekly `VACUUM` when idle.
6. If the file is corrupt, it is quarantined, a fresh queue is started and a repair issue is
   raised. It never blocks transport.

## Consequences

- One small state file to back up. Content in it is plaintext at rest inside the app's
  `/data` (threat T55). Encryption at rest is **not** proposed: the key would sit beside it.
- Receipts distinguish "delivered" (recipient proof) from "stored on node". The UI must never
  call the latter delivered (MS-6).
