# Contributing to MeshBeacon

Thank you for your interest. MeshBeacon is in **Phase 0 (research and design)**: the most useful
contributions right now are reviews of, and corrections to, the documents in [`docs/`](docs/).

## Before you start

- Read the [vision](docs/vision.md), [architecture](docs/architecture.md) and
  [threat model](docs/security/threat-model.md).
- For anything non-trivial, open an issue to discuss it first.
- **Security issues:** follow [SECURITY.md](SECURITY.md), not the public tracker.

## Ground rules

1. **No upstream code copying.** Do not copy, translate or paraphrase source code from Reticulum,
   LXMF, Rathole, Sideband, NomadNet, RNode firmware or other projects into MeshBeacon. Use the
   upstream packages as dependencies through their public interfaces. See
   [licensing research §3](docs/research/licensing.md#3-copying-versus-depending).
2. **No protocol or cryptography implementations.** If a change needs one, it belongs upstream.
3. **No monkeypatching of RNS or LXMF**, and no access to their private attributes
   ([ADR 0001](docs/adr/0001-networking-foundation.md)).
4. **Privacy and security defaults are not negotiable in a pull request.** Changing a default
   (host networking, ports, discovery, permissions, telemetry) needs an ADR.
5. **Tests are part of the change.** See the [testing strategy](docs/testing/strategy.md). Tests
   must never connect to live Reticulum networks or a live Home Assistant instance.
6. **British English** in documentation, comments and user-facing text.
7. **Keep it small.** Prefer readable code over clever code; the core should stay reviewable in a
   sitting.

## Labelling claims in documentation

Research and design documents distinguish **[Verified]**, **[Assumption]**,
**[Recommendation]** and **[Open]** statements. Verified statements must cite a primary source
(upstream file and revision, official documentation, or a reproducible test).

## Commits and pull requests

- Work on a feature branch; never commit directly to `main`.
- One logical change per pull request, with a clear description of *why*.
- Sign off your commits under the [Developer Certificate of Origin](https://developercertificate.org/)
  (`git commit -s`) — **[Proposed]**, to be confirmed alongside the licence decision.
- Pull requests need review and approval by the maintainer before merging.

## AI assistance

AI tools may be used to *assist* contributions. In keeping with the expectations of the Reticulum
and Home Assistant communities:

- **Disclose it.** Say in the pull request if substantive parts were drafted with an AI tool. Do
  not remove or obscure attribution (for example, an assistant's commit identity or co-author
  line) that a tool adds.
- **Own it.** You must have reviewed, understood and be able to explain and defend every line you
  submit, without the tool's help. Unreviewed AI output will be closed.
- **No autonomous submissions.** Agents must not open issues or pull requests, or reply to review
  comments, on a contributor's behalf without that person's review.
- **Do not paste upstream source into AI tools to have it reproduced or translated** (see rule 1).
- **Do not contribute to upstream Home Assistant / Open Home Foundation repositories with
  autonomous agents** — their AI policy forbids it.

The Phase 0 documents themselves were drafted with an AI assistant at the maintainer's direction,
committed under the assistant's own Git identity, and are subject to the maintainer's review.

## Licence of contributions

No licence has been chosen yet ([licensing research](docs/research/licensing.md)). Until one is
added, please limit contributions to review comments and discussion; code contributions cannot be
accepted before the project has a licence.
