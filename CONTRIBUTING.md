<picture>
  <source media="(prefers-color-scheme: dark)" srcset="branding/png/logo-horizontal-dark.png">
  <img src="branding/png/logo-horizontal-light.png" alt="ito" height="48">
</picture>

# Contributing to ito

Thank you for your interest. ito is in **Phase 0 (research and design)**: the most useful
contributions right now are reviews of, and corrections to, the documents in [`docs/`](docs/).

## Before you start

- Read the [vision](docs/vision.md), [architecture](docs/architecture.md) and
  [threat model](docs/security/threat-model.md).
- For anything non-trivial, open an issue to discuss it first.
- **Security issues:** follow [SECURITY.md](SECURITY.md), not the public tracker.

## Ground rules

1. **No upstream code copying.** Do not copy, translate or paraphrase source code from Reticulum,
   LXMF, Rathole, Sideband, NomadNet, RNode firmware or other projects into ito. Use the
   upstream packages as dependencies through their public interfaces. See
   [licensing research §4](docs/research/licensing.md#4-copying-versus-depending).
2. **No protocol or cryptography implementations.** If a change needs one, it belongs upstream.
3. **No monkeypatching of RNS or LXMF**, and no access to their private attributes
   ([ADR 0001](docs/adr/0001-networking-foundation.md)).
4. **Privacy and security defaults are not negotiable in a pull request.** Changing a default
   (host networking, ports, discovery, external connections, permissions, telemetry, the
   non-root service user) needs an ADR.
5. **Validate all user input against allow-lists** and render configuration only through
   structured APIs — never by string templating ([architecture §4.1](docs/architecture.md#41-settings-validation-and-injection-safe-configuration-rendering)).
6. **Ease of use counts.** A change that makes setup harder for a non-technical user needs a good
   reason, stated in the pull request.
7. **Tests are part of the change.** See the [testing strategy](docs/testing/strategy.md). Tests
   must never connect to live Reticulum networks or a live Home Assistant instance.
8. **British English** in documentation, comments and user-facing text.
   Never include household-specific identifiers (IP or Tailscale addresses, hostnames, SSIDs,
   identity hashes) in issues, logs or test records — use placeholders such as `<lan-ip>`.
9. **Keep it small.** Prefer readable code over clever code; the core should stay reviewable in a
   sitting.

## Labelling claims in documentation

Research and design documents distinguish **[Verified]**, **[Assumption]**,
**[Recommendation]** and **[Open]** statements. Verified statements must cite a primary source
(upstream file and revision, official documentation, or a reproducible test).

## Commits and pull requests

- Work on a feature branch; never commit directly to `main`.
- One logical change per pull request, with a clear description of *why*.
- Sign off your commits under the [Developer Certificate of Origin](https://developercertificate.org/)
  (`git commit -s`). By signing off you confirm you have the right to submit the work under the
  project's licence.
- Pull requests need review and approval by the maintainer before merging.

## AI assistance

AI tools may be used to *assist* contributions. In keeping with the expectations of the Reticulum
and Home Assistant communities:

- **Authorship (maintainer decision, 19 Nov 2026).** Commits are made under the contributor's own
  authenticated GitHub identity. Do not add AI co-author trailers to commits, and do not add AI
  attribution to pull request descriptions. **Never falsify authorship:** a tool must not commit
  under a person's identity without that person's own authentication, and existing history is not
  rewritten (earlier commits made under an assistant's Git identity stay as they are). How the
  project uses AI assistance is stated once, at project level, in the README.
- **Own it.** You must have reviewed, understood and be able to explain and defend every line you
  submit, without the tool's help. Unreviewed AI output will be closed.
- **No autonomous submissions.** Agents must not open issues or pull requests, or reply to review
  comments, on a contributor's behalf without that person's review.
- **Do not paste upstream source into AI tools to have it reproduced or translated** (see rule 1).
- **Training opt-out.** Only use AI tools under terms where your inputs and outputs are not used to
  train models (for example an API or business agreement, or a consumer account with training
  turned off). The Reticulum License forbids use of RNS/LXMF "directly or indirectly" in creating
  training datasets, so giving RNS material to a tool that trains on inputs is a licence risk.
  Prefer giving AI tools RNS's documentation and public API rather than its source. See
  [licensing §6](docs/research/licensing.md#6-the-reticulum-licenses-ai-training-condition-and-ai-assisted-development).
- **No datasets.** Never build or publish corpora, embeddings or transcripts containing RNS or
  LXMF material.
- **Do not contribute to upstream Home Assistant / Open Home Foundation repositories with
  autonomous agents** — their AI policy forbids it.

The Phase 0 documents themselves were drafted with an AI assistant at the maintainer's direction,
committed under the assistant's own Git identity, and are subject to the maintainer's review.

## Licence of contributions

ito is licensed under [Apache-2.0](LICENSE) ([ADR 0002](docs/adr/0002-licence.md)).
Contributions are accepted under the same licence, with a DCO sign-off. Do not contribute
material you cannot licence under Apache-2.0 — including anything copied from Reticulum-licensed,
GPL or Creative Commons sources.

Until Phase 1 is approved, contributions are limited to documentation review and discussion.
