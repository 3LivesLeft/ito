# ADR 0009: Isolate public services from Home Assistant and from the transport process

- **Status:** **Accepted as an architectural requirement** (maintainer, 19 November 2026). The
  process and IPC mechanism is **deliberately deferred** until a security review and physical
  Raspberry Pi memory measurements are available (see "Deferral").
- **Date:** 19 November 2026
- **Deciders:** MeshBeacon maintainer
- **Evidence:** [Forward-compatibility review F-1, F-4](../research/long-term-direction.md#f-1-process-model-for-lxmf-and-later-services),
  [ADR 0005](0005-bounded-recovery.md), [ADR 0006](0006-local-metrics-api.md),
  [vision, architectural principle 4](../vision.md#architectural-principles-for-the-long-term-direction)
- **Extends:** ADR 0005 (bounded recovery of one RNS child) and ADR 0006 (read-only status API).
  Supersedes nothing.

## Context

Proposed milestones from v0.4 add **public** services that accept requests and content from
strangers: pages, bulletin boards, libraries, propagation. They are the largest new attack surface
in the roadmap. Today one child process (`meshbeacon.node`) holds the RNS instance, with
`share_instance = No` (architecture §5, §9), and ADR 0005's recovery rules assume that child.

## Decision

1. **Isolation from Home Assistant.** Public services have no route to Home Assistant's APIs,
   data, configuration, events or entities, and no route into any private control interface
   between Home Assistant and MeshBeacon. They never receive the Supervisor token, the status API
   token or any HA credential. What Home Assistant may *see* about them is limited to the
   read-only status API (ADR 0006), extended only by a later ADR.
2. **Separate failure domain from transport.** A public service **should not share a single
   failure domain with the transport process**: a crash, hang, memory exhaustion or flood in a
   public service must not stop, restart or starve Reticulum transport. Each service has its own
   bounded recovery state in the style of ADR 0005, and a failing service is stopped, not allowed
   to cascade.
3. **Resource limits per service**: storage quota, rate limits and memory bounds of its own
   (architectural principle 5).
4. Private messaging (the v0.3 messaging milestone) is **not** a public service, but its design
   must not prevent this separation later.

## Deferral (maintainer, 19 November 2026)

No process or IPC implementation is chosen now. The choice is made only once both are available:

| Input | What is needed |
|---|---|
| Security review | Of each candidate, especially a shared RNS instance with a local socket and `rpc_key` (feasibility Q-6): reach from other apps (namespaces, abstract sockets, trust boundary B4), key handling, failure isolation |
| Raspberry Pi memory | Measured on the physical reference device (not QEMU): idle RSS + swap of each candidate layout with transport, messaging and one stand-in service, against the 128 MB idle target (RG-1 method) |

Until then, designs keep a per-service boundary inside the core (own start, stop, health and
recovery state) so that any of the options below remains possible.

## Options to evaluate (not chosen)

| Option | Isolation | Cost |
|---|---|---|
| Services in separate processes attached to a shared RNS instance | Separate failure domain | Opens a local RNS socket guarded by `rpc_key` (feasibility Q-6); security-default change needing an ADR |
| Services in the RNS child with in-process guards | Weak: one failure domain | Contrary to decision 2 |
| Separate container or app per service class | Strongest | Memory, set-up complexity, five-minute goal |

## Consequences

- The process model for messaging and later services must be chosen against decision 2
  (feasibility Q-35).
- The 128 MB idle target may need restating per deployment profile once several processes run.

## Review triggers

The first public service design; any proposal for a public service to read Home Assistant data
(for example sensor sharing in proposed v0.7, which then needs its own ADR and per-sensor opt-in).
