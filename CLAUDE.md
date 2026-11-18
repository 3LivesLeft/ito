# CLAUDE.md

Guidance for AI coding assistants (including Claude Code) working in this repository. Humans:
see [CONTRIBUTING.md](CONTRIBUTING.md), which takes precedence over this file.

## Project in one paragraph

MeshBeacon is a free, privacy-first Home Assistant app (formerly "add-on") that runs the
**unmodified** Reticulum reference implementation (RNS, and later LXMF) and surfaces it in Home
Assistant. It is currently in **Phase 0: research and documentation only**. There is no
application code. Do not start Phase 1 work until the maintainer explicitly approves it.

## Hard rules

1. **Do not copy upstream source.** Never reproduce, translate or paraphrase code from RNS, LXMF,
   Rathole, Sideband, NomadNet or RNode firmware into this repository. Use upstream packages as
   pinned dependencies through public APIs, config files and CLI tools only.
2. **No protocol, cryptography or networking-protocol implementations.**
3. **No monkeypatching** of RNS/LXMF and no use of their private (`_`/`__`-prefixed) attributes.
4. **Never weaken security defaults** (host network, ports, Supervisor/Core API access,
   capabilities, AppArmor, discovery, auto-connect, publishing of addresses or locations,
   telemetry) without an ADR approved by the maintainer.
5. **Never log, print, commit or echo private keys, RPC keys or tokens.** Do not create or commit
   real identity files; tests generate throwaway identities in temporary directories.
6. **Never connect to live Reticulum networks or public entry points**, and never deploy to a
   live Home Assistant instance. Tests use isolated networks only (see
   [docs/testing/strategy.md](docs/testing/strategy.md)).
7. **Do not add or change the project licence** — it is a pending maintainer decision.
8. **Do not merge to `main`** and do not push to branches other than the one you were asked to
   use. Open pull requests only when asked.
9. **Disclose provenance honestly.** Do not strip or hide AI attribution. Keep commit authorship
   as configured.
10. **Do not post to upstream Home Assistant / Open Home Foundation projects** — their AI policy
    forbids autonomous agent contributions.

## Writing conventions

- British English (organisation, licence (noun) / license (verb), behaviour, colour, initialise).
- In research/design docs, label statements **[Verified]**, **[Assumption]**,
  **[Recommendation]** or **[Open]**, and cite primary sources with upstream versions or commit
  hashes. Do not present unverified upstream behaviour as fact.
- Keep documents concise; prefer tables for comparisons.
- Home Assistant now calls add-ons "apps"; write "app (formerly add-on)" on first use.

## Repository map

```text
README.md, CONTRIBUTING.md, SECURITY.md, CLAUDE.md
docs/vision.md                     why, principles
docs/architecture.md               proposed structure (core vs HA adapters)
docs/roadmap.md                    versions + v0.1.0 acceptance criteria
docs/research/feasibility.md       Phase 0 research, open questions (Q-n), risks (R-n)
docs/research/licensing.md         licence analysis (no licence chosen)
docs/security/threat-model.md      assets, threats (T-n), controls
docs/testing/strategy.md           isolated-network testing approach
docs/adr/NNNN-*.md                 architecture decision records
```

## When Phase 1 is approved (for reference, not yet)

- Core package must not import Home Assistant; the HA integration must not import `RNS`.
- Pin Python dependencies by hash; pin base images by digest.
- Every change ships with tests; run the full isolated-network suite before changing the RNS pin.
- Update the relevant ADR, threat model and open-question tables when a decision is made.
