# Bundled dashboard review — 21 November 2026

These are screenshots of the production Ingress HTTP handler and shared frontend, served at a
nested Home Assistant ingress path. A fake Supervisor and messaging engine supply test data;
this is not a deployment to a real Home Assistant installation.

| View | Preview |
|---|---|
| Phone setup, light | [390 px](settings-390-light.png) |
| Tablet setup, dark | [820 px](settings-820-dark.png) |
| Desktop overview, light | [1280 px](overview-1280-light.png) |

Browser validation covered Overview, Messages, Diagnostics and Settings at 390, 820 and 1280 px
in light and dark modes (24 combinations). No page errors, horizontal overflow or axe WCAG
2.2 AA violations were reported. A light-theme messaging status badge found during validation
was corrected. See [browser results](browser-results.json).

The browser also selected Emerald, enabled messaging, saved through the real HTTP handler,
observed a simulated app restart and checked that the saved configuration returned. It then
created a contact and sent a fixture message through the Ingress messaging route. Real LXMF
transport and persistence are covered by the repository's existing isolated-network tests.

Local validation: 574 Python unit tests passed (45 Unix-socket tests deselected because this
execution environment forbids Unix sockets); 129 Home Assistant tests passed; 70 frontend tests
passed. Branding generation, frontend bundle consistency, release layout, Ruff and core/HA
strict type checks passed. Full socket/container, messaging and AppArmor coverage runs in GitHub CI.

Before release, verify a fresh install and in-place update on Home Assistant OS with Supervisor
2026.11+: default sidebar entry, administrator access, preset selection, Save and apply,
reconnection and messages in both directions. Confirm the existing Reticulum/LXMF identities,
contacts and conversation history remain. This physical installation check was not performed.

Existing optional Marketplace integrations may need one update to rename their old sidebar
panel to **ito history**. The bundled app dashboard then has a single update path with the app.
