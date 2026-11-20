# ADR 0017: Node services are independent of Home Assistant

- **Status:** **Accepted** (maintainer, 19 Nov 2026, decision P-5). Documentation only: no future
  service is implemented in v0.3.
- **Date:** 19 November 2026
- **Related:** [ADR 0008](0008-messaging-process.md) (messaging process),
  [ADR 0014](0014-messaging-engine-contract.md) (engine contract),
  [long-term direction](../research/long-term-direction.md), [vision](../vision.md)

## Context

The roadmap's longer-term direction includes public Reticulum services, offline pages, community
bulletin boards, knowledge libraries and short push-to-talk voice messages
([roadmap](../roadmap.md#long-term-direction-proposed)). Communities must be able to rely on them
when Home Assistant is restarting, being updated or absent. Home Assistant is MeshBeacon's
first-class management interface today, and must stay so, but it must not become a runtime
dependency of the network services.

## Decision

```text
 MeshBeacon node runtime (the HA-free core package; packaged today as a Home Assistant app)
 ├─ core supervisor           bounded restarts, health, settings source
 ├─ RNS node process          transport, shared instance
 ├─ services                  each its own supervised process, off by default,
 │    ├─ messaging (LXMF)     v0.3 (ADR 0008, 0014)
 │    └─ pages, boards, libraries, voice   later, each with its own ADR and threat review
 ├─ management contract       versioned: status, settings, contacts, services (+ messaging v1)
 └─ bindings                  thin, replaceable: the HA integration today; other clients later
```

1. **Services never import Home Assistant or HTTP-server code**, and bindings never import RNS or
   LXMF. ADR 0014's boundary applies to every service, enforced by architecture tests.
2. **Network services keep running while Home Assistant Core is stopped or unreachable.** Only
   management and presentation pause. A service never waits for Home Assistant to start, to
   acknowledge or to answer.
3. **Settings come through one source.** Today that is the Supervisor's `options.json`; later it
   may be a file, for packaging outside Home Assistant. No service reads Supervisor paths itself.
4. **Each service has its own identity scope, storage quota under `/data/<service>/`, rate limits
   and failure isolation**, as ADR 0008 sets out for messaging. A failing service never stops
   transport.
5. **Public-facing services** (public pages, boards, propagation for strangers) are off by default
   and need their own ADR and threat review before design, like the v0.4 public-gateway work.
   **[Open]** the licences of upstream components such as LXST (voice), checked when that work
   starts.
6. **Home Assistant remains a first-class management interface:** entities, repairs, the sidebar
   panel and, from v0.3, authorised messaging commands. It is one binding of the management
   contract, never the place where a service's state lives.

## Consequences

- A new service is a new process plus a contract binding; the Home Assistant integration gains a
  view of it without owning it.
- Acceptance criterion **SA-1** for every service: with Home Assistant Core stopped, the service
  keeps working, and its queued data reaches Home Assistant once it returns.
- Packaging the core outside Home Assistant (for example a plain container) stays possible without
  redesign. It is not planned.
- The Supervisor-specific parts (discovery, the discovery relay, `options.json`) stay at the edge,
  in the core supervisor and its bindings.

## Review triggers

Any service that would need Home Assistant to be running; any proposal to keep service state in
Home Assistant; any public-facing service.

## Amendment (maintainer, 19 Nov 2026): process isolation is mandatory

Decision 4's "own identity scope, storage quota, rate limits and failure isolation" is made
concrete and binding: **each service, the management core and Reticulum run as separate Unix
users**, with least-privilege access to credentials, storage and IPC, proven by adversarial
isolation tests. This must be **implemented** before any additional community service is
introduced and before M4 is accepted; an ADR alone is not sufficient
([roadmap](../roadmap.md#process-isolation-gate-mandatory), IS-1 to IS-4). Today only the
discovery credential is isolated, and by kernel dumpable and ptrace rules rather than by user
(threat T72).
