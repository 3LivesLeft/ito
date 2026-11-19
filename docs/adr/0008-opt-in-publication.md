# ADR 0008: Explicit opt-in for announcements and publication

- **Status:** **Accepted** (maintainer, 19 November 2026)
- **Date:** 19 November 2026
- **Deciders:** MeshBeacon maintainer
- **Evidence:** [Forward-compatibility review F-3](../research/long-term-direction.md#f-3-consent-to-announce),
  [architecture §5](../architecture.md#5-networking-posture), CLAUDE.md hard rules 4 and 14
- **Extends:** the v0.1 privacy defaults (nothing published, discovered or connected without the
  user's choice) and [ADR 0004](0004-public-peer-presets.md) (no default connection). Supersedes
  nothing.

## Context

Receiving LXMF messages, hosting pages and running community services all require announcing
destinations on the Reticulum network **[Assumption]**, and some also publish content. An announce
reveals that a destination exists and can be linked to the node. v0.1 and v0.2 announce and
publish nothing beyond what RNS itself does for transport.

## Decision

1. **Nothing is announced or published by default**, in any version. Every announce of a
   destination owned by MeshBeacon (messaging, pages, boards, propagation, any later service) and
   every publication of content requires the user's **explicit opt-in for that service**.
2. Consent is **per service**, never a single "publish everything" switch, and switching a service
   off stops its announces and publication.
3. Each opt-in is explained in plain language at the point of choice: what becomes visible, to
   whom, and what cannot be withdrawn once others have copied it.
4. Interface discovery and publication features of RNS (`discoverable`, `publish_ifac`,
   `location_cmd`, `AutoInterface`, and similar) stay off; turning any on still needs its own
   ADR under hard rule 4.
5. Defaults for announce frequency respect RNS's native announce cap and, on radio links, airtime
   limits (architectural principle 3).
6. One shared consent model is used by every service, so later services reuse it rather than
   inventing their own.

## Consequences

- A fresh installation is unreachable for messaging until the user opts in; this is deliberate and
  must be explained in the first-run text when messaging ships.
- Every service design (from the v0.3 messaging milestone on) must state which destinations it
  announces and what it publishes, and pass that through this model.

## Review triggers

Any proposal to announce or publish by default; an RNS or LXMF change in what announces contain.
