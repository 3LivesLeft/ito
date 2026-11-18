# ADR 0007: A sidebar panel served by the integration

- **Status:** **Accepted as the interim dedicated interface** (maintainer, 18 Nov 2026): the
  integration panel is retained until a secure built-in replacement is available, and it remains
  the only dedicated interface. Its presentation code is delivery-independent
  ([architecture §6a](../architecture.md)), so a later built-in interface reuses it. History of
  this status: proposed, then recommended for withdrawal (below), then retained after the Ingress
  security review.
- **Earlier status:** **Proposed; recommended for withdrawal.** The maintainer's out-of-the-box principle
  (18 Nov 2026) requires the dedicated interface to come with the app itself, without the
  integration. [ADR 0013](0013-built-in-interface-ingress.md) proposes delivering it through
  Ingress and moving this panel's code into the app. If ADR 0013 is accepted, this ADR is
  superseded and the integration's panel is removed before release. Until then, the
  implementation stays on the v0.2 branch for review.
- **Date:** 18 November 2026
- **Evidence:** this ADR's tests (`tests/ha/test_panel.py`, `tests/frontend/model.test.mjs`),
  the real Home Assistant 2026.11.2 smoke test (`tools/ha_smoke_test.py`), and the
  [threat model T37–T42](../security/threat-model.md)

## Context

The maintainer asked for MeshBeacon to feel like a standalone application in Home Assistant, with
its own sidebar entry and icon, set up automatically or with minimal effort. It should have a
modern, responsive design in light and dark themes, large figures, colour-coded connectivity,
traffic, processor and memory history, peer cards, and clear loading, unavailable and error
states. It must use no external frontend dependencies or CDN requests, no duplicate collection or
history storage, and no unnecessary permissions or public endpoints. It must be able to grow into
Overview, Peers, Messages, Interfaces and Diagnostics tabs, but only v0.2.0 features may be shown,
with no empty placeholder tabs.

## Options considered

| | A. Native dashboard (`show_in_sidebar`) | **B. Custom panel registered by the integration** | C. Supervisor Ingress (app-served web UI) | D. Dashboard + custom cards (HACS frontend) |
|---|---|---|---|---|
| Own sidebar entry and icon | Yes | **Yes** | Yes (`panel_icon`) | Yes |
| Set-up effort | A storage dashboard cannot be created through a public API. The user pastes YAML, or the integration writes Lovelace's private storage | **None: appears when the integration loads, goes when it unloads** | None, but only once Ingress is enabled in the app | The user installs a frontend package, adds a resource and builds a dashboard |
| Design freedom | Low: built-in cards only (no large-figure grid, peer cards or combined states) | **Full** | Full | High |
| History | Recorder (native cards) | **Recorder, through HA's websocket API** | The app would need its own store, or `homeassistant_api` to read HA's (**a new permission; it lowers the security rating**) | Recorder |
| New permissions or listeners | None | **None in the app.** One read-only websocket command in HA, admins only | `ingress: true`, a new web server in the app, and probably `homeassistant_api`. The project forbids `ingress` (`tests/unit/test_app_config.py`) | None |
| Works without the Supervisor (HACS-only install) | Yes | **Yes** | No | Yes |
| Third-party code | None | **None** (plain custom element, no build step) | Whatever the app's UI uses | A card library or our own card bundle |
| Maintenance | Low, but limited | **Low to medium: one ~30 KB module, pure logic unit-tested in Node** | High: a second UI, server, authentication path and store | Medium to high: card API churn, two places to configure |

**[Verified]** against Home Assistant 2026.10.4 and 2026.11.2:
`panel_custom.async_register_panel` (`homeassistant/components/panel_custom/__init__.py`) and
`frontend.async_remove_panel` exist and are used by the tests. Static files are served with
`hass.http.async_register_static_paths`. History comes from the existing
`history/history_during_period` and `recorder/statistics_during_period` websocket commands. A
non-iframe panel shares the page with Home Assistant, so the user's theme variables (light, dark or
custom) apply without extra code.

## Decision

**Option B.** The integration registers a custom panel at `/meshbeacon`. It has the title
"MeshBeacon" and the icon `mdi:access-point-network`, which is the node's status icon.

1. **Code.** `custom_components/meshbeacon/frontend/` holds `meshbeacon-panel.js` (the custom
   element) and `model.js` (pure functions for formatting, history, downsampling, chart geometry
   and view states). There is no framework, no third-party code, no build step, no bundler and no
   CDN. A test fails if either file contains an external URL, `fetch`, `XMLHttpRequest`,
   `innerHTML`, `eval` or browser storage.
2. **Data.** Live values come from `hass.states`, which HA already pushes to the page. History
   comes from HA's recorder: raw history for 6 h and 24 h, and hourly long-term statistics for
   7 days. The panel stores nothing, collects nothing and never contacts the app.
3. **Entity mapping.** One websocket command, `meshbeacon/panel`, is read-only and **admins only**.
   It returns, for each loaded entry, the entity IDs of its *enabled* entities and its peers'
   names. Disabled entities are left out, so the panel never shows empty widgets.
4. **Exposure.** The panel is `require_admin=True`. The module is served from
   `/meshbeacon_panel/`, which contains only the two JS files. Like all HA frontend files it can be
   fetched without logging in, so it contains no data. A version hash in the module URL stops
   browsers keeping a stale copy.
5. **Lifecycle.** The panel is registered when the first entry loads and removed when the last one
   unloads. Static paths and the command are registered once per HA start.
6. **Security in the page.** Every value is written with `textContent`, never parsed as HTML, and
   SVG is built with `createElementNS`, so a peer name cannot inject markup (tested with a hostile
   name in the preview).
7. **Tabs.** There are two tabs, both with real v0.2 content: **Overview** (connectivity, figures,
   history, peers) and **Diagnostics** (status, problem, start times, restarts, memory breakdown,
   detail sensors when enabled). The route is `/meshbeacon/<tab>`. Peers, Messages and Interfaces
   are added only when there is something to put in them (Peers when per-interface detail arrives,
   Messages with LXMF). `TABS` in `model.js` is the single list, and an unknown tab path falls back
   to Overview.
8. **Resources.** Charts use 120 buckets. History is fetched at most once per bucket width (at
   least 60 s), only while the page is visible. The page re-renders only when one of its own
   entities changes.

The example YAML dashboard (`docs/home-assistant/dashboard.yaml`) stays as an alternative for
people who prefer native cards. It needs no maintenance beyond the existing entity test.

## Consequences

- The integration now depends on `frontend`, `http`, `panel_custom` and `websocket_api`. These are
  core components loaded in every standard installation. The pytest harness installs the
  frontend version that HA 2026.10.4 pins.
- The panel relies on documented frontend conventions: the `hass`, `narrow`, `route` and `panel`
  properties, HA theme CSS variables, and the `ha-menu-button` and `ha-icon` elements. The last two
  are used only if they are defined; without them the panel still works, just without the menu
  button or icons. A future frontend change could affect layout but not data or security.
- The panel's text is UK English only. Entity states are formatted with `hass.formatEntityState`,
  which uses the integration's translations. Translating the panel's own text is future work.
- Non-admin users see no sidebar entry. Entity states remain visible to them under Home
  Assistant's normal rules. Changing `REQUIRE_ADMIN` is a one-line decision for the maintainer.
- **Rejected: Ingress (C).** It would add a web server and an authentication path inside the app.
  It would need its own history store (duplicate storage) or a new Home Assistant API permission
  (a lower rating). It contradicts the approved posture (`ingress` is forbidden in
  `config.yaml`).

## Review triggers

Revisit if Home Assistant offers a supported way for integrations to create dashboards, if the
custom-panel API changes, or if a future tab needs data that is not in entities. Messages, for
example, would need a new ADR under v0.3.
