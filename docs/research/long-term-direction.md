# Long-term direction: forward-compatibility review of v0.3

Status: **Review for the maintainer; nothing here is implemented.** Several findings were decided
by the maintainer on 19 November 2026 (ADRs 0018–0021); see the Status column. · Date: 19 November
2026 · Roadmap: [roadmap §Long-term direction](../roadmap.md#long-term-direction-proposed)

Labels: **[Verified]**, **[Assumption]**, **[Recommendation]**, **[Open]** (see
[feasibility.md](feasibility.md#how-to-read-this-document)). Upstream behaviour is not stated as
fact unless it was verified in earlier phases at the versions cited there (RNS 1.6.0, LXMF 1.3.0).

## 1. Purpose

The maintainer has agreed a long-term direction: MeshBeacon grows from a household Reticulum node
into an offline-first community network (messaging, Nomad Network-compatible pages, community
services, voice bursts, resilient infrastructure), with Home Assistant as a first-class
deployment and management interface but not a dependency of the community services.

This document asks one question: **which decisions due in v0.3 could, if taken narrowly, prevent
that direction?** It does not redesign v0.3, add to its scope or choose between options. Each
finding names the decision, why it matters later, and what a v0.3 ADR should at least consider.
All recommendations need the maintainer's approval before they affect any design.

## 2. Summary

v0.3 is now split ([ADR 0021](../adr/0021-v0.3-scope.md)): v0.3.0 distribution, then a gated
messaging milestone. "v0.3" below means whichever of the two takes the decision.

| ID | v0.3 decision | Later capability at risk | Severity | Question | Status (19 Nov) |
|---|---|---|---|---|---|
| F-1 | How LXMF runs alongside RNS (process model) | Pages (v0.4), propagation and boards (v0.5), replication (v0.7) | **High** | Q-35 | Requirement set ([ADR 0020](../adr/0020-public-service-isolation.md)); mechanism open (MG-5) |
| F-2 | Which identity LXMF uses | Separate public service addresses; identity compatibility (principle 8) | **High** | Q-36 | Decided: separate identities ([ADR 0018](../adr/0018-separate-identities.md)), subject to validation |
| F-3 | How "announce my address" is consented to | Every public service (v0.4+) | **High** | Q-37 | Decided: per-service opt-in ([ADR 0019](../adr/0019-opt-in-publication.md)) |
| F-4 | The Home Assistant → core path for sending messages | Isolation of public services from HA (principle 4) | **High** | Q-38 | `notify` removed; send path needs its own ADR (MG-1, MG-2) |
| F-5 | Where contacts, conversations and delivery state are stored | Standalone deployments (principle 7) | Medium | Q-39 | Open (MG-6) |
| F-6 | Message size, delivery-method and timeout defaults | LoRa links (principle 3), voice bursts (v0.6) | Medium | — | Gate MG-7 |
| F-7 | Storage quota and backup treatment of messages | Boards, libraries, replication (v0.5, v0.7) | Medium | Q-44 | Open (MG-6) |
| F-8 | Whether the optional propagation node stays in v0.3 | Community propagation services (v0.5) | Medium | Q-40 | Decided: proposed v0.5 |
| F-9 | Publishing the app for store installation | Name, slug and data layout become permanent | **High** | Q-41, Q-43, Q-45 | Q-43, Q-45 resolved ([v0.3 distribution](v0.3-distribution.md)); naming open, blocks v0.3.0 ([naming §5–6](naming.md#6-availability-and-collision-assessment-commonwave-19-november-2026)) |
| F-10 | Status API schema when messaging metrics are added | Radio interfaces, multiple services | Low | — | Unchanged |
| F-11 | Memory budget with LXMF loaded | Running several services on one small device | Low | — | Unchanged |

## 3. Findings

### F-1 Process model for LXMF and later services

- **[Verified]** v0.1 renders `share_instance = No`, so RNS opens no local socket or RPC listener,
  and only the `meshbeacon.node` child holds the RNS instance (architecture §5, §9).
- **[Assumption]** Every later service (LXMF router, page hosting, propagation, boards) must use
  that same RNS instance; a second instance would need its own interfaces.
- Risk: if v0.3 places the LXMF router in `node.py` ad hoc, each later service is added to the
  same process. A fault in a bulletin board could then restart the transport node, and per-service
  memory and recovery cannot be bounded separately (ADR 0005 assumes one child).
- The alternative, a shared instance that separate service processes attach to, changes a security
  default (a local socket guarded by `rpc_key`; feasibility Q-6) and needs an ADR.
- **[Recommendation]** The v0.3 ADR should choose the model with v0.4–v0.7 services in view, and
  keep a per-service boundary inside the core (own start, stop, health and recovery state) whichever
  model is chosen.

### F-2 Identity for LXMF

- **[Verified]** MeshBeacon owns one identity today, the transport identity, with atomic creation,
  validation before every start, a verified backup and no silent replacement (architecture §4.6).
  The threat model already lists a separate LXMF delivery identity as asset A2.
- Risk: reusing the transport identity as the messaging address ties routing to a public address,
  and later services (a page node, a propagation node) would have to share it too or be bolted on
  without the same protections.
- **[Recommendation]** Generalise the identity manager to named identities, one per role, each with
  the same guarantees. Keep the v0.1 transport identity's file, format and location unchanged so
  that existing installations keep their identity (principle 8); any migration is additive.
- **[Open]** Identity import (deferred since v0.2) matters for users bringing an existing LXMF
  address from another client; the v0.2 requirements in architecture §4.6 still apply.

### F-3 Consent to announce

- **[Assumption]** Receiving LXMF messages requires announcing a delivery destination; hosting
  pages or a propagation node requires announcing further destinations.
- **[Verified]** Hard rule 4 forbids weakening defaults on discovery and publication without an
  approved ADR; v0.1 publishes nothing.
- Risk: a messaging-only "announce" switch in v0.3 would be repeated, slightly differently, for
  each later service.
- **[Recommendation]** The v0.3 ADR should define one consent model for announcing, off by default,
  explicit per service, explained in plain language, and reusable by v0.4+ services.

### F-4 Home Assistant → core control path

- **[Verified]** ADR 0006 makes the status API read-only by decision; there are no write
  endpoints. The previously agreed v0.3 `notify` platform needs HA to send messages through the
  core, so it needs a write path and therefore a new or amended ADR.
- Risk: a general-purpose write API would become the obvious way for later public services to
  reach Home Assistant, contrary to principle 4.
- **[Recommendation]** Make the v0.3 path a narrow, private interface (send a message; read delivery
  state) reachable only from Home Assistant, never from Reticulum. Public services from v0.4 must
  have no route into it or into HA. Received messages should reach HA only as the user chooses,
  since HA's recorder would otherwise keep message metadata.

### F-5 Where messaging data lives

- Risk: contacts or conversations held as HA options, config entries or entity attributes would
  not exist in a standalone deployment (principle 7), and would place message metadata in HA's
  database and backups.
- **[Recommendation]** Keep the authoritative store under the core's `/data` (LXMF's own storage
  plus any MeshBeacon contact list), schema-versioned, with Home Assistant only displaying it.
  Supervisor options remain for settings, not data.

### F-6 LoRa-aware defaults

- v0.3 will be tested over TCP only. Defaults chosen there (attachment sizes, retry counts,
  delivery method, how long before a message is shown as failed) become user expectations.
- **[Recommendation]** Conservative message-size limits; no automatic attachments; delivery states
  that can express "still trying" for hours, not TCP-scale timeouts. Interoperating clients may put
  extra LXMF fields (for example audio) in messages **[Assumption]**; v0.3 should keep or ignore
  unknown fields rather than reject messages, so that v0.6 voice is not blocked.

### F-7 Storage quotas and backups

- **[Verified]** v0.1 guards storage with a 200 MB free-space floor and a 100 MB cap on regenerable
  RNS directories; backups are `hot` with RNS caches excluded.
- **[Recommendation]** Implement any v0.3 limit (message store, propagation node) as one instance
  of a general per-service quota, and decide explicitly whether messages are included in Home
  Assistant backups (privacy and size).

### F-8 Propagation node placement

- The optional propagation node is a previously agreed v0.3 item; the new direction places "LXMF
  propagation services" in v0.5. It would also be the first MeshBeacon service that stores data
  from strangers, so it sets the precedent for principle 5 (quotas, rate limits, abuse handling).
- **Decided (ADR 0021):** moved to proposed v0.5, designed as a public service under ADRs 0019
  and 0020.

### F-9 Publishing for store installation

- **[Verified]** ADR 0003: the slug and image name are effectively permanent once installed, so a
  rename must be decided before the first image is published. Publishing is gated on release
  gates RG-1 to RG-12 and needs explicit maintainer approval.
- **[Assumption]** The existing MeshBeacon project describes itself as communications that keep
  working when the internet does not (naming research §1.1). The new community, offline-first
  direction moves this project closer to it in purpose and audience than the household framing
  assessed in ADR 0003.
- **[Verified]** (Home Assistant 2026.11.2; [v0.3 distribution](v0.3-distribution.md)) The backend
  app is installed from the Supervisor **App store** (a repository with `repository.yaml`); the
  integration from the Core **Marketplace** (needs `hacs.json`; catalogue `hacs/default`). Q-43 and
  Q-45 are resolved. Any such submission must be made by the maintainer personally (CLAUDE.md rule 10).
- **[Open] Q-41** (Commonwave assessed in [naming §6](naming.md#6-availability-and-collision-assessment-commonwave-19-november-2026)).

### F-10 Status API schema

- **[Verified]** Schema 1 models connectivity as configured TCP peers. Radio interfaces and several
  services do not fit that model well.
- **[Recommendation]** Add messaging figures, if any, additively under a new schema version rather
  than overloading peer fields.

### F-11 Memory budget

- **[Verified]** The idle target is ≤ 128 MB for all app processes; v0.2 measured about 71 MiB
  with monitoring on (container, not Pi).
- **[Recommendation]** Measure LXMF's cost separately in v0.3 so later services can be budgeted.

## 4. Points for later milestones (not v0.3)

| Topic | Note |
|---|---|
| Nomad Network compatibility (v0.4) | Interoperate through published formats and behaviour only; check the licences of Nomad Network and any page-format renderer before use **[Open]**; hard rule 1 forbids copying |
| Voice codecs (v0.6) | Check codec licences against Apache-2.0 and the image's licence allow-list **[Open]** |
| LoRa regulation | Regional airtime and duty-cycle limits (UK: Ofcom IR 2030 **[Assumption]**, threat model §4) |
| RNode hardware | Device mapping changes the security posture (hard rule 4) and the AppArmor profile; needs an ADR |
| Remote automation | Remains private (allow-listed identities) and separate from public services (principle 4); external design review before implementation, as previously agreed |
| Sensor sharing (v0.7) | Publishing Home Assistant data to a community is a privacy decision per sensor, off by default |
