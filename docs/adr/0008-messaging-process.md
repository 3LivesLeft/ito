# ADR 0008: LXMF runs in its own supervised process

- **Status:** **Proposed — awaiting independent review.** Not to be implemented until reviewed and approved by the maintainer.
- **Date:** 18 November 2026
- **Evidence:** [v0.3 feasibility and architecture](../research/v0.3-messaging.md), [threat model T43–T58](../security/threat-model.md)

## Context

Messaging must not endanger the node's core job: staying connected and relaying. LXMF is used
unmodified (rules 1 and 3). Its router keeps state on disk, runs its own job loop and may spend
seconds generating stamps. The Pi's memory budget is tight (v0.2: 78 MiB at 7 minutes against
a 128 MB budget).

## Options

| | A. Inside the RNS node process | **B. Separate process, RNS shared-instance client** | C. Upstream `lxmd` daemon |
|---|---|---|---|
| Failure isolation | None: a messaging fault or stall stops transport | **A crash or stall affects only messaging** | Good |
| Cost when messaging is off | Code loaded, but idle | **Zero: not started** | Zero |
| Memory when on | Lowest | Second RNS client: **[Open] Q-40**, budget ≤ +40 MiB | Similar to B |
| API for HA, queue, contacts | Mixed into the node process | **Clean boundary** | No delivery API; it is a propagation daemon |
| Restart policy | Shared with transport | **Independent, bounded (ADR 0005 style)** | Its own |

## Decision

**B.** The core supervisor starts `meshbeacon.messaging` only when messaging is on. It connects to
the node's RNS shared instance (unique `instance_name`, explicit `rpc_key`, as in v0.1). It runs
`LXMRouter` through public APIs only. It exposes a small local control channel to the core (a
pipe, the same pattern as the status line). The core serves the HA API and forwards requests.
Bounded restarts: 5 in 30 minutes, then pause with a repair issue. `nice` is +5, and stamp
generation has a CPU time limit.

## Consequences

- The process is reached only through the Messaging Service contract (ADR 0014); it contains no
  Home Assistant or interface code.

- One more process to supervise and test, and one more AppArmor path (`/data/messaging/`).
- Prototype gate: if Q-40 shows the second process costs more than 40 MiB, revisit A with
  in-process watchdogs. That decision would come back to review.
- Q-46: the client must survive RNS node restarts. This is a reliability test before release.

## Amendment (maintainer, 19 Nov 2026): mandatory process isolation

The messaging process **must run as its own Unix user**, separate from the core and from
Reticulum, with least-privilege access to its credentials, `/data/messaging/` and its IPC
channels, proven by adversarial tests. This must be **implemented** before M4 is accepted; this
ADR alone does not satisfy it ([roadmap](../roadmap.md#process-isolation-gate-mandatory), IS-1 to IS-4).

**[Open]** The decision above has the core start the process. An unprivileged core cannot start,
signal or memory-limit a process of another user, which is why Reticulum still shares the core's
user today (M1.2, threat T72). The M4 design must therefore choose, and review, how separate
services are started and supervised (for example s6 services with per-user run scripts and a
narrow control channel to the core, or a minimal reviewed privileged launcher), and must apply the
same answer to Reticulum.
