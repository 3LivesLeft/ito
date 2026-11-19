# ADR 0012: Optional propagation node (phase 3b)

- **Status:** **Proposed — awaiting independent review.** Not to be implemented until reviewed and approved by the maintainer.
- **Date:** 18 November 2026
- **Evidence:** [v0.3 feasibility and architecture](../research/v0.3-messaging.md), [threat model T43–T58](../security/threat-model.md)

## Context

A propagation node stores encrypted messages for offline recipients and syncs with peer nodes.
LXMF provides it (`enable_propagation`, storage limits, authentication, static peers, peering
costs). On a home Pi it consumes disk, memory and bandwidth, and it accepts data from strangers.

## Decision

1. Off by default. It is a separate option, and it is delivered **after** core messaging.
2. **Static peers only** (`from_static_only`), auto-peering off, `max_peers` 4.
3. Quota `message_storage_limit` 64 MiB by default (maximum 1 GiB, and never more than 25 % of free
   space at start); LXMF's 30-day expiry; `propagation_limit` kept at the LXMF default.
4. Optional authentication (`set_authentication`, `allow`), so the node can serve only the
   household's contacts. **[Recommendation]** on by default when the node is enabled.
5. Propagation stamps are enforced (LXMF default costs), so strangers pay to store.
6. Metrics: stored messages, store size, peers, syncs. Counts only.

## Consequences

- Without a node of its own, MeshBeacon can still use any trusted node as its inbound and
  outbound node (phase 3a).
- Public-node operation (auto-peering, no authentication) needs its own review, like the v0.4
  public-gateway work.
