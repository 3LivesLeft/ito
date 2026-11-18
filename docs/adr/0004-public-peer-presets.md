# ADR 0004: Optional, verified public peer presets; no default connection

- **Status:** Accepted
- **Date:** 18 November 2026
- **Evidence:** [Public peer presets research](../research/public-peers.md),
  [first-run UX](../ux/first-run.md)

## Context

A non-technical user should be connected to Reticulum within five minutes. Choosing a peer by
hand is the hardest step. Well-known public entry points exist (for example Ratspeak's Ruby,
Emerald and Diamond servers), but connecting to them exposes the user's IP address to their
operators, and the project must not depend on any provider.

## Decision

1. MeshBeacon makes **no external connection by default.** With no peers configured, it runs as
   an isolated node and says so clearly.
2. The configuration offers **optional presets**, selected explicitly by the user (zero or more),
   **alongside** free-form custom peers, which are always available.
3. Presets are stored as **data** with operator, endpoint, interface type, operator rules and a
   verification record.
4. A preset is shipped only after the manual verification checks V1–V7 in the research document
   have passed against the exact pinned RNS version within 30 days of the release.
5. Presets are only shipped when at least **two independent operators** have passed verification,
   so that no single provider becomes the de-facto default. Until then the preset list is empty
   and the documentation explains how to add a peer manually.
6. The privacy explanation in research §4 is shown in the option description and in `DOCS.md`.

## Consequences

- The five-minute target depends on verified presets; without them the first-run flow needs one
  more step (typing a peer address from the documentation). The UX document plans for both.
- Shipping a preset is a release-time responsibility for the maintainer, which takes ongoing
  effort; presets that fail re-verification are removed.
