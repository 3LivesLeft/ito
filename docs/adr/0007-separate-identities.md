# ADR 0007: Separate identities for transport, messaging and public services

- **Status:** **Accepted, subject to technical validation** (maintainer, 19 November 2026). The
  validation items below must pass before any code relies on this decision.
- **Date:** 19 November 2026
- **Deciders:** MeshBeacon maintainer
- **Evidence:** [Forward-compatibility review F-2](../research/long-term-direction.md#f-2-identity-for-lxmf),
  [architecture §4.6](../architecture.md#46-identity-crash-safe-initialisation-and-restoration),
  [threat model A1, A2](../security/threat-model.md#1-assets)
- **Extends:** architecture §4.6 (one MeshBeacon-owned transport identity). Supersedes nothing.

## Context

Since v0.1 MeshBeacon owns one identity, the Reticulum transport identity, with atomic creation,
validation before every start, a verified backup and no silent replacement (LP-6, LP-7). LXMF
messaging needs a delivery identity, and future public services (pages, boards, propagation) need
addresses of their own. Reusing the transport identity everywhere would link routing to every
public address and make it impossible to retire one role without changing all of them.

## Decision

1. MeshBeacon keeps **separate identities per role**: the Reticulum transport identity; an LXMF
   messaging identity; and one identity per future public service (or per service class, to be
   settled when each service is designed).
2. **The existing transport identity is never replaced or regenerated** by this change, by any
   migration, or by the introduction of any new role. Its file, format and location stay as in
   v0.1 (`/data/reticulum/storage/transport_identity` and its verified backup). New identities are
   added alongside it; migration is additive only.
3. Every identity receives the same protections as the transport identity: MeshBeacon-owned atomic
   creation, validation before use, a verified backup, no silent replacement, no key material or
   hashes in logs (hard rules 5 and 13).
4. A new identity is created only when the user first enables the role that needs it; nothing is
   created or announced by default (see [ADR 0008](0008-opt-in-publication.md)).

### Identity replacement rules (maintainer, 19 November 2026)

| ID | Rule |
|---|---|
| IR-1 | **Automatic upgrades, migrations and normal restarts never replace or regenerate any identity.** This covers app updates, schema or storage migrations, the introduction of new roles, restores from backup, recovery and safe mode |
| IR-2 | The existing **user-initiated** *"Replace identity on next start"* option (architecture §4.6 item 5, LP-6) is **preserved** |
| IR-3 | Explicit replacement **requires a confirmation step** in addition to switching the option on, and **explains its consequences** before anything changes: the node gets a new address; peers, paths and contacts that knew the old address will not recognise it; the previous identity is kept in the data folder and in backups; identities of other roles (messaging, public services) are not affected unless replaced separately |
| IR-4 | Each role's identity can be replaced only individually and only through IR-2/IR-3; there is no "replace all" |

## Technical validation required

| ID | To validate | How |
|---|---|---|
| IV-1 | LXMF accepts a delivery identity distinct from the transport identity, through public APIs only | Isolated-network test (RNS 1.6.0, LXMF 1.3.0 or the pin then current) |
| IV-2 | Several identities in one RNS instance (or across the processes chosen under ADR 0009) behave as expected, with no private-attribute access | Isolated-network test |
| IV-3 | An installation upgraded from v0.1/v0.2 keeps a byte-identical transport identity and fingerprint, and no migration path can reach the replacement code (IR-1) | Upgrade and migration tests from a v0.2 `/data` fixture with a throwaway identity |
| IV-4 | Crash-safety of creating each new identity (the LP-7 method) | Randomised-kill test |
| IV-5 | Memory and storage cost per identity is negligible against the 128 MB target | Measurement |

If any item fails, this ADR returns to the maintainer before an alternative is designed.

## Consequences

- Losing or rotating a public-service identity does not change the node's transport address or
  the user's messaging address.
- More key files to back up; Home Assistant backups already include `/data`.
- The identity manager must be generalised from one identity to named identities, keeping the
  transport identity's existing code path and tests intact.

## Resolved point and implementation gap

The open point recorded earlier the same day (whether the user-requested replacement option stays)
is **resolved by IR-2: it stays**.

**[Verified]** The current implementation (v0.1/v0.2) satisfies IR-1 and IR-2:

- replacement is a journalled transaction;
- it happens only when the user switches the option on, and MeshBeacon refuses to start while
  the option is left on afterwards (LP-6).

It does **not yet** satisfy IR-3. The option is a single switch, and its description
(`translations/en.yaml`, `DOCS.md`) mentions only the new address and the kept old identity.

**[Open]** How to add the confirmation step is not chosen; it is an implementation decision for
the maintainer. Options include a second confirmation field, a confirmation in the optional
integration, or a two-start handshake. Supervisor options cannot show a dialog.

## Review triggers

IV-1 to IV-5 failing; an LXMF or RNS release that changes how identities are loaded; a request to
import identities from other clients (identity import remains unscheduled).
