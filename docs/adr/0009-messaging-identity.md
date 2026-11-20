# ADR 0009: A separate messaging identity

- **Status:** **Proposed — awaiting independent review.** Not to be implemented until reviewed and approved by the maintainer.
- **Date:** 18 November 2026
- **Evidence:** [v0.3 feasibility and architecture](../research/v0.3-messaging.md), [threat model T43–T58](../security/threat-model.md)

## Context

The node already has a transport identity, which is crash-safe, validated before start and
restorable (architecture §4.6). LXMF needs an identity for its delivery destination, which
becomes the household's messaging address that contacts store.

## Decision

1. Use a **separate messaging identity**, stored at `/data/messaging/identity` (0600, owned by the
   service user). It is created on first enable, validated before every start (rule 13), and
   never logged (rule 5).
2. **Backup and restore** follow the same crash-safe pattern as the transport identity, with
   their own "replace" option. Replacing one never touches the other.
3. Use **one identity per installation** in v0.3. Per-person identities are out of scope (Q-45).
4. The announced display name is **empty by default** and user-settable.
5. Ratchets stay on (LXMF default). Ratchet files live under `/data/messaging/`.

## Consequences

- The address contacts know survives a transport identity replacement, and the reverse.
- **[Assumption]** separation limits the damage of key compromise. It does not stop an observer
  correlating the two, because both are announced from the same node. This is documented in the
  privacy statement.
- Two identities appear in the app's backup. The documentation recommends encrypted HA backups
  (threat T2).
