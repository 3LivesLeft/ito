# M4 — Standalone LXMF messaging engine: implementation plan

**Status:** **for the maintainer's approval.** Nothing is implemented. **Branch:**
`feature/m4-lxmf-engine`, from `feature/v0.3.0-install-ready` at `ff050d3`. **Date:** 19 November 2026.

## Goal

A messaging engine that runs on its own, independently of Home Assistant: its own process and
user, its own identity, a persistent queue with honest receipts, and the versioned Messaging
Service contract v1 (ADR 0014). It is **off by default** and **absent from production images**
until M4's gate is passed. It is built only through public LXMF and RNS APIs (CLAUDE.md rules 1,
3 and 11).

## Scope

| In M4 | Not in M4 |
|---|---|
| Process isolation by user for the core, Reticulum and the engine (ADR 0018; gate IS-1 to IS-4) | Home Assistant messaging, its key and the panel's Messages view (M5) |
| Engine process `meshbeacon.messaging` (ADR 0008) with contract v1 (ADR 0014) | Hosting a propagation node (ADR 0012: after core messaging) |
| Messaging identity (ADR 0009): separate, 0600, validated before every start | Per-person identities (Q-45), telemetry, location, LXST voice |
| Queue and receipts (ADR 0011); **use** of a configured propagation node | Ingress or any built-in interface (ADR 0013 is blocked) |
| Engine–core binding: the local socket of ADR 0018 | Any user-facing option in production `config.yaml` |
| A development image and a development-only CLI for tests | Publishing anything |

## Work packages

| WP | Content | Done when |
|---|---|---|
| **WP1 Isolation** (first; it also hardens today's app) | ADR 0018: users 9100, 9101 and 9102; s6 services `reticulum`, `rns-prepare` and `messaging` start down; `s6-svperms` for the core's group; FIFOs for output and status; ownership of `/data/<service>/` at every start; `owner` AppArmor rules | IS-1 to IS-4 pass: an adversarial container test as each user, under AppArmor in CI, also run against a weakened build; existing identities unchanged across upgrade **and** downgrade; ADR 0005 timings and every existing container test unchanged; idle memory ±2 MiB |
| **WP2 Spike** (time-boxed, go/no-go) | Engine as `mb-lxmf` reaching the RNS shared instance across users; Q-40 (memory), Q-46 (survives RNS restarts), Q-41 (stamp time) | ≤ +40 MiB idle with messaging on, or the plan returns for review |
| **WP3 Engine** | Router through the public API; identity (ADR 0009); contacts from a development-only file in `/data/messaging/`; inbound policy (contacts only, signature-validated; stamps for "anyone"; size and rate limits); queue and receipts (ADR 0011) | MS-2 to MS-6, MS-8 to MS-10 and MS-16 pass with real LXMF on loopback, and `lxmd` for MS-6 |
| **WP4 Contract and binding** | Contract v1 over the ADR 0018 socket, with peer checks both ways; the core supervises the engine (bounded restarts) and exposes **nothing** new to Home Assistant | MS-15 and MS-21 pass; contract tests run against the real engine behind a fake binding |
| **WP5 Packaging** | `lxmf` hash-pinned in a separate `meshbeacon/requirements-messaging.txt`; Dockerfile build argument, off by default; CI builds a development image for messaging tests | A test proves the production image contains no LXMF, no `messaging` service and no messaging option (MS-1 also measured); the release dry run is unchanged |
| **WP6 Evidence** | MS-19 (SD-card writes); the isolated interoperability set-up for MS-14 | Automated results in CI; manual and hardware items recorded as M4 acceptance blockers |

## Acceptance

**M4 is accepted only when all of these hold:**

- IS-1 to IS-4;
- MS-1 to MS-6, MS-8 to MS-10, MS-15, MS-16, MS-19 and MS-21;
- **MS-14:** interoperability with Sideband 2.3.x and Ratspeak 1.1.x on an isolated network (manual, needs devices);
- **MS-18:** Pi resources on a spare Pi.

MS-7, MS-11, MS-12, MS-13, MS-20 and MS-22 belong to M5 (Home Assistant). MS-17 belongs to propagation-node hosting.

## Dependencies and pins

- **LXMF 1.3.0** (requires `rns>=1.6.0`; works with the pinned RNS 1.6.0).
- **LXMF 1.3.1** requires RNS ≥ 1.6.1, which was released on 19 Nov 2026. Move to it only after a
  cooling-off period and the full isolated-network suite (CLAUDE.md: before changing the RNS pin), as
  a separate change.
- Q-43 (whether 1.3.0 and 1.3.1 interoperate) is part of MS-14.

## Risks

| Risk | Handling |
|---|---|
| s6 control or the FIFOs miss ADR 0005's timings | Tested in WP1; fallback is ADR 0018 option B, back to review |
| The shared instance is not reachable across users, or not after an RNS restart | WP2 spike, decided before WP3 starts |
| Memory or stamp CPU on a Pi 4 | Q-40 and Q-41 in the spike; MS-18 on a spare Pi |
| Reticulum License conditions | Public APIs only; no upstream code copied or paraphrased; source read only to verify behaviour, cited by file and revision |
| WP1 changes the production app | It lands in a release **after** v0.3.0 (M2 ships M1 as reviewed), with its own VM re-test added to RG-13 |

## Decisions needed

| ID | Decision | Recommendation |
|---|---|---|
| **D-M4-1** | Isolation design | ADR 0018 option A (s6, no new root code) |
| **D-M4-2** | LXMF pin | 1.3.0 now; 1.3.1 with RNS 1.6.1 later, separately |
| **D-M4-3** | Propagation node | Use a configured node in M4; hosting one later |
| **D-M4-4** | Contacts in M4 | A development-only file; user-facing configuration with M5 |
| **D-M4-5** | Order | WP1, then WP2, then WP3 to WP5, then WP6; one draft PR, opened only when asked |

## Decisions after the spike (maintainer, 19 Nov 2026)

- **D-M4-6:** a narrow IS-3 exception for the RNS shared-instance socket only (roadmap IS-3a).
- **D-M4-7:** continue. +40 MiB stays the binding criterion, measured on the spare Pi (MS-18); the
  container reading is a warning, and the engine avoids loading what it does not use.

## Progress (19 Nov 2026)

**WP1 (isolation) is complete:** `87a249e`. CI is green on the real base image, including amd64
under AppArmor enforcement and aarch64. The core runs as 9100 and Reticulum as 9101 through s6.
The isolation probe passes as each user and detects a deliberately weakened container. The identity
is unchanged across upgrade and downgrade. Idle memory is 69.5 MiB (baseline 69.2 MiB).

The isolation probe also found that s6-overlay leaves the container environment, which holds the
Supervisor token, readable by every user. This is fixed here and on the v0.3.0 branch (`2fb2192`).

**WP2 spike: two gate decisions needed.** Measured in a throwaway container, with LXMF 1.3.0 and
RNS 1.6.0:

| Question | Result |
|---|---|
| The engine (`mb-lxmf`) uses Reticulum (`mb-rns`) across users through the shared instance | **Works** |
| Q-46: it survives a Reticulum restart | **Works:** offline during the restart, reconnected by itself about 16 s later |
| Q-40: the engine's idle memory | **43.1 MiB** (RSS + swap, amd64); the go/no-go limit is +40 MiB |
| IS-3: who can reach the shared instance | **Any process in the app container.** RNS 1.6.0 uses abstract Unix sockets on Linux (`RNS/Reticulum.py`, lines 369 and 816–826): no file permissions and no peer check. RPC needs a key that only `mb-rns` holds. Other apps cannot reach it (each container has its own network namespace) |
