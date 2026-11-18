# CLAUDE.md

Guidance for AI coding assistants (including Claude Code) working in this repository. Humans:
see [CONTRIBUTING.md](CONTRIBUTING.md), which takes precedence over this file.

## Project in one paragraph

MeshBeacon is a free, privacy-first Home Assistant app (formerly "add-on") that runs the
**unmodified** Reticulum reference implementation (RNS, and later LXMF) and surfaces it in Home
Assistant. Phase 0 (research and design) is complete. **Phase 1 (v0.1.0 foundation) is authorised** on
branch `feature/v0.1.0-foundation` (PR #2). **v0.2.0 (monitoring and observability) is authorised**
on branch `feature/v0.2.0-observability` (draft PR #3), based on PR #2's reviewed head `192db5f`;
ADR 0006 is accepted, and its option stays off by default permanently. ADR 0007 (integration sidebar panel) is accepted as the interim
dedicated interface; Ingress (ADR 0013) is blocked. HACS is prepared, not published. v0.3.0 is in research and architecture only (no
implementation until independently reviewed). LXMF, LoRa, I2P and remote control remain out of scope. Never publish images, create releases, connect to live public Reticulum
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

- **Out-of-the-box usability is a permanent product principle** ([vision](docs/vision.md)
  principle 2, maintainer, 18 Nov 2026). Treat it like a hard rule:
  - The dedicated MeshBeacon interface must come with the standard app installation, with no
    separate custom integration, HACS or manual dashboard configuration required.
  - A first-time user can install, configure and start MeshBeacon within five minutes, with no
    terminal and no YAML.
  - The Home Assistant integration is an optional enhancement (entities, custom dashboards,
    statistics, automations); nothing essential may depend on it.
  - It never overrides security, privacy or resource principles. Do not duplicate monitoring
    logic to achieve it.
  - The proposed delivery is Supervisor Ingress ([ADR 0013](docs/adr/0013-built-in-interface-ingress.md)).
    It is **blocked by security review**: do not enable or implement Ingress, and never treat
    read-only as a mitigation for session exposure. Read-only is a temporary restriction, not
    the product's limit ([secure interface options](docs/research/secure-interface-options.md)).
  - Do not publish or commit details of security findings under responsible disclosure.
- **Consistent branding is a permanent product principle** ([vision](docs/vision.md) principle 3;
  [docs/branding.md](docs/branding.md)):
  - Use the brand assets in `branding/` (generated by `tools/brand/build.py` from
    `branding/src/`; never hand-edit generated files or crop the concept image).
  - Interface views use only the design tokens in `custom_components/meshbeacon/frontend/tokens.js`
    and the documented components.
  - In Home Assistant's sidebar and entity icons, use Material Design Icons only
    (`mdi:lighthouse-on` for MeshBeacon).
  - Keep WCAG 2.2 AA (the contrast test, never colour alone, reduced motion).
  - Never load fonts or anything else from external services.
  - Update docs/branding.md in the same change as any new pattern.
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
docs/home-assistant-integration.md  v0.2 integration: set-up, entities, panel, dashboard
docs/hacs.md                       HACS compatibility (prepared, not published)
docs/research/known-paths.md       why "Known paths" reads 2,048 (RNS unused-path target)
docs/testing/v0.2-physical-results.md  initial physical readings (not final acceptance)
docs/testing/v0.2-acceptance-review.md  open criteria, CI status, risks, simplest installation
docs/getting-started.md            tester guide: app, then the optional sidebar integration
custom_components/meshbeacon/       v0.2 Home Assistant integration
custom_components/meshbeacon/frontend/  interface (ADR 0007): plain JS, no dependencies; layers in
                                   docs/architecture.md §6a: sources/ (data), ui/ (presentation),
                                   meshbeacon-panel.js (delivery shell for the integration panel)
tests/frontend/                    panel unit tests (`node --test tests/frontend/model.test.mjs`)
tools/panel_preview.html           panel preview with sample data (loopback only)
hacs.json                          HACS metadata (no release workflow)
docs/branding.md                   visual identity, colours, type, tokens, accessibility
branding/                          brand assets: src/ (master SVGs), svg/, png/, fonts/ (OFL)
tools/brand/                       asset build (build.py, render.mjs, outline_wordmark.py)
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
only to `GET /api/v1/status`, schema 1). The sidebar panel (ADR 0007) reads only HA entities and
HA's recorder: no third-party JS, no CDN, no `innerHTML`, no browser storage (tests enforce this).
The HA test harness needs `home-assistant-frontend` (in `requirements-ha-test.txt`).
Keep the interface layers separate: views read only the view-data contract (`model.js`
NODE_KEYS/PEER_KEYS); only `sources/` knows where data comes from; only the delivery shell knows
its host. Metrics are computed only in `core/meshbeacon/metrics.py`;
read only allow-listed RNS counters and report anything unavailable as `null`, never as zero.

Layout: `meshbeacon/` is the app folder (Supervisor build context); `meshbeacon/core/meshbeacon/`
is the HA-free core; only `prepare.py` and `node.py` import RNS. Child processes are started with
`python -u` (RNS logs with `print()`).

## Rules carried over from Phase 0

- Core package must not import Home Assistant; the HA integration must not import `RNS`.
- Pin Python dependencies by hash; pin base images by digest.
- Every change ships with tests; run the full isolated-network suite before changing the RNS pin.
- Update the relevant ADR, threat model and open-question tables when a decision is made.
