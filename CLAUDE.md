# CLAUDE.md

Guidance for AI coding assistants (including Claude Code) working in this repository. Humans:
see [CONTRIBUTING.md](CONTRIBUTING.md), which takes precedence over this file.

## Project in one paragraph

MeshBeacon is a free, privacy-first Home Assistant app (formerly "add-on") that runs the
**unmodified** Reticulum reference implementation (RNS, and later LXMF) and surfaces it in Home
Assistant. Phase 0 (research and design) is complete. **Phase 1 (v0.1.0 foundation) is authorised** on
branch `feature/v0.1.0-foundation` (PR #2). **v0.2.0 (monitoring and observability) is authorised**
on branch `feature/v0.2.0-observability`, based on PR #2's reviewed head `192db5f` and kept separate
from it; ADR 0006 (local status API and Supervisor discovery) is accepted in principle, its security review
is recorded and PR #3 is merged; its option stays off by default permanently. Next, v0.3.0 is an installation and distribution release only (ADR 0021);
LXMF messaging is a later, gated v0.3 milestone; ADRs 0018–0020 (separate identities, opt-in
publication, public-service isolation) constrain it. LXMF, LoRa, I2P and remote control remain out of scope. Never publish images, create releases, connect to live public Reticulum
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
docs/research/v0.2-observability.md  v0.2 feasibility, architecture, security review
docs/home-assistant-integration.md  v0.2 integration: set-up, entities, dashboard
docs/research/long-term-direction.md  v0.3 forward-compatibility review (proposed v0.4+ direction)
docs/research/v0.3-distribution.md  App store and Marketplace installation (HA 2026.11.2)
custom_components/meshbeacon/       v0.2 Home Assistant integration
```

## Developing (Phase 1 and v0.2)

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/ruff check meshbeacon/core tests tools && .venv/bin/ruff format --check meshbeacon/core tests tools
.venv/bin/mypy
.venv/bin/pytest -m "not container"            # unit + isolated-network integration (loopback only)
docker buildx build --load -t meshbeacon:dev meshbeacon
MESHBEACON_IMAGE=meshbeacon:dev .venv/bin/pytest -m container tests/container
# Home Assistant integration (needs Python 3.14 and requirements-ha-test.txt):
mypy --strict --python-version 3.14 custom_components/meshbeacon
python -m pytest tests/ha -o "pythonpath=meshbeacon/core ." -o asyncio_mode=auto
```

v0.2: `custom_components/meshbeacon/` is the HA integration (never imports RNS or the core; talks
only to `GET /api/v1/status`, schema 1). Metrics are computed only in `core/meshbeacon/metrics.py`;
read only allow-listed RNS counters and report anything unavailable as `null`, never as zero.

Layout: `meshbeacon/` is the app folder (Supervisor build context); `meshbeacon/core/meshbeacon/`
is the HA-free core; only `prepare.py` and `node.py` import RNS. Child processes are started with
`python -u` (RNS logs with `print()`).

## Rules carried over from Phase 0

- Core package must not import Home Assistant; the HA integration must not import `RNS`.
- Pin Python dependencies by hash; pin base images by digest.
- Every change ships with tests; run the full isolated-network suite before changing the RNS pin.
- Update the relevant ADR, threat model and open-question tables when a decision is made.
