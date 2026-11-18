# ADR 0002: Licence MeshBeacon's original work under Apache-2.0

- **Status:** Accepted (maintainer preference, following independent review)
- **Date:** 18 November 2026
- **Evidence:** [Licensing research](../research/licensing.md)

## Context

Phase 0 deliberately left the licence unselected. The independent review stated a preference for
Apache-2.0. MeshBeacon depends on RNS and LXMF, which are under the Reticulum License (an
MIT-style grant with conditions on harmful use and AI-training use; not OSI-approved). Its
container image will also contain GPL, MPL and permissive components from the Home Assistant
Alpine base image.

## Decision

1. MeshBeacon's **original code and documentation** are licensed under the **Apache License,
   Version 2.0**. `LICENSE` and `NOTICE` are added to the repository.
2. MeshBeacon is described as *open source (Apache-2.0)*. Its **container image** is described as
   an aggregate that also contains third-party components under their own licences, including
   Reticulum-licensed RNS/LXMF, which are **not** OSI-approved.
3. Contributions are accepted under Apache-2.0 with a **Developer Certificate of Origin**
   sign-off. No CLA.
4. No upstream source is copied into the repository.
5. **No image is published** until the obligations O1–O7 in licensing §5 are implemented in CI
   (notices, SBOM, GPL corresponding source, licence allow-list).
6. AI assistance continues to be disclosed, and the AI-tool rules in licensing §6.4 apply.

## Consequences

- Compatible with depending on RNS/LXMF (no GPL-style "no further restrictions" conflict) and with
  Home Assistant's own Apache-2.0 tooling.
- Explicit patent grant and patent-retaliation clause protect users and contributors.
- Users of the image remain bound by the Reticulum License for RNS/LXMF; documentation must say so.
- CI work is needed for SBOM, notices and source bundles before the first release.

## Alternatives considered

MIT (simpler, no patent grant); Reticulum License for MeshBeacon itself (values-aligned but
non-OSI); GPL-3.0/AGPL-3.0 (rejected: conflict with the Reticulum License's conditions).
