# CLAUDE.md

Guidance for AI coding assistants (including Claude Code) working in this repository. Humans:
see [CONTRIBUTING.md](CONTRIBUTING.md), which takes precedence over this file.

## Project in one paragraph

MeshBeacon is a free, privacy-first Home Assistant app (formerly "add-on") that runs the
**unmodified** Reticulum reference implementation (RNS, and later LXMF) and surfaces it in Home
Assistant. Phase 0 (research and design) is complete. **Phase 1 (v0.1.0 foundation) is authorised** on
branch `feature/v0.1.0-foundation`, starting after PR #1 is merged. Do not begin v0.2.0 work
without approval. Never publish images, create releases, connect to live public Reticulum
infrastructure or deploy to the maintainer's Home Assistant without explicit approval.

## Hard rules

1. **Do not copy upstream source.** Never reproduce, translate or paraphrase code from RNS, LXMF,
   Rathole, Sideband, NomadNet or RNode firmware into this repository. Use upstream packages as
   pinned dependencies through public APIs, config files and CLI tools only.
2. **No protocol, cryptography or networking-protocol implementations.**
3. **No monkeypatching** of RNS/LXMF and no use of their private (`_`/`__`-prefixed) attributes.
4. **Never weaken security defaults** (host network, ports, Supervisor/Core API access,
   capabilities, AppArmor, discovery, auto-connect, publishing of addresses or locations,
   telemetry) without an ADR approved by the maintainer.
5. **Never log, print, commit or echo private keys, RPC keys, tokens or identity/destination
   hashes** (not even during identity replacement). Do not create or commit
   real identity files; tests generate throwaway identities in temporary directories.
6. **Never connect to live Reticulum networks or public entry points**, and never deploy to a
   live Home Assistant instance. Tests use isolated networks only (see
   [docs/testing/strategy.md](docs/testing/strategy.md)).
7. **The licence is Apache-2.0** ([ADR 0002](docs/adr/0002-licence.md)). Do not change it, and
   do not add material that cannot be licensed under it.
8. **Do not merge to `main`** and do not push to branches other than the one you were asked to
   use. Open pull requests only when asked.
9. **Disclose provenance honestly.** Do not strip or hide AI attribution. Keep commit authorship
   as configured.
10. **Do not post to upstream Home Assistant / Open Home Foundation projects** — their AI policy
    forbids autonomous agent contributions.
11. **Never build or publish datasets, corpora or bulk copies of RNS/LXMF material.** Prefer RNS's
    documentation and public API over its source; when source must be read to verify behaviour,
    cite file and revision and do not reproduce it (Reticulum License AI condition — licensing §6).
12. **Never render RNS configuration by string templating.** Validate every user field against an
    allow-list and use ConfigObj's object API, then round-trip-check the result.
13. **Never let RNS start with an unvalidated identity** — RNS silently replaces corrupt identity
    files.
14. **No external connections by default.** The health endpoint fails only when the core is
    unresponsive — never for connectivity or `needs_attention` states (ADR 0005).
15. **Never commit household-specific identifiers** — private or public IP addresses, Tailscale
    addresses or node names, MAC addresses, hostnames, SSIDs, HA URLs or Reticulum identity hashes
    from the maintainer's or anyone's installation. Use placeholders such as `<lan-ip>`.

## Product principles to keep in mind

- Ease of use is a core principle: a non-technical user connected within five minutes. Prefer
  safe defaults and plain-language messages over options.
- v0.1.0 is deliberately small (see [docs/roadmap.md](docs/roadmap.md)): no dashboards, LXMF, I2P,
  LoRa, remote automation, TCP listener or raw config.

## Writing conventions

- British English (organisation, licence (noun) / license (verb), behaviour, colour, initialise).
- In research/design docs, label statements **[Verified]**, **[Assumption]**,
  **[Recommendation]** or **[Open]**, and cite primary sources with upstream versions or commit
  hashes. Do not present unverified upstream behaviour as fact.
- Keep documents concise; prefer tables for comparisons.
- Home Assistant now calls add-ons "apps"; write "app (formerly add-on)" on first use.

## Repository map

```text
README.md, CONTRIBUTING.md, SECURITY.md, CLAUDE.md, LICENSE, NOTICE
docs/vision.md                     why, principles
docs/architecture.md               proposed structure (core vs HA adapters)
docs/roadmap.md                    versions + v0.1.0 acceptance criteria
docs/research/feasibility.md       Phase 0 research, open questions (Q-n), risks (R-n)
docs/research/licensing.md         licence analysis (Apache-2.0 chosen; obligations)
docs/research/naming.md            the existing "MeshBeacon" project; trademarks
docs/research/public-peers.md      optional public peer presets and verification
docs/ux/first-run.md               five-minute setup path; option and message design
docs/security/threat-model.md      assets, threats (T-n), controls
docs/testing/strategy.md           isolated-network and reference-environment testing
docs/testing/reference-environment.md  maintainer's reference device (no household identifiers)
docs/adr/NNNN-*.md                 architecture decision records
```

## When Phase 1 is approved (for reference, not yet)

- Core package must not import Home Assistant; the HA integration must not import `RNS`.
- Pin Python dependencies by hash; pin base images by digest.
- Every change ships with tests; run the full isolated-network suite before changing the RNS pin.
- Update the relevant ADR, threat model and open-question tables when a decision is made.
