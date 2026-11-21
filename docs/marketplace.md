<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../branding/png/logo-horizontal-dark.png">
  <img src="../branding/png/logo-horizontal-light.png" alt="MeshBeacon" height="48">
</picture>

# The integration in Home Assistant's Marketplace

**Status:** `hacs.json` and the integration layout are ready on `develop`, but the default
branch (`main`) is not yet ready for Marketplace installation. Marketplace repository links
resolve the default branch; `main` currently lacks `hacs.json` and has older integration code.
Do not tell users to install from Marketplace until a reviewed release brings the complete,
tested integration and `hacs.json` to `main`. The first GitHub release and any catalog listing
also require maintainer approval ([releasing](releasing.md)).
Facts and sources: [v0.3 installation research](research/v0.3-install.md).

## What the Marketplace reads from this repository

| Item | Where | Checked by |
|---|---|---|
| `hacs.json` | repository root (and every release tag) | `tools/check_release.py`, `tests/unit/test_hacs.py` |
| Keys | `name` and `homeassistant` (`2026.11.0`) only; no ZIP release, no content in root | same |
| The integration | `custom_components/meshbeacon/` with `manifest.json`, `brand/` and the panel files in `frontend/` | same |
| The app store files | `repository.yaml` and `meshbeacon/` sit beside it; the Marketplace installs the integration and ignores them | `tools/check_release.py` |

## How users get it (after the default branch is release-ready)

1. In the ito app's **Documentation** tab, or the README, select **Add the ito
   dashboard** (My link `marketplace_repository`, owner `3LivesLeft`, repository `ito`,
   category `integration`).
2. Until ito is in the catalog, the Marketplace first asks to **connect GitHub** (a code to
   enter at github.com; read-only, public data only) and to confirm adding the repository.
3. The first time only, accept the Marketplace's warning.
4. **Install**, then follow the setup page or the restart repair.

Updates then appear under **Settings → Updates**. After an integration update, Home Assistant asks
for a restart through a repair.

## Development branches and the default branch

The app store and the Marketplace are separate installation mechanisms. An app repository URL
with `#develop` selects the app's development branch; it does **not** make the Marketplace
install the custom integration from that branch. The Marketplace's repository URL is the
canonical `https://github.com/3LivesLeft/ito`, and it needs a valid `hacs.json` and current
integration on the default branch. Do not add a placeholder `hacs.json` to an old `main` on its
own: that could expose an outdated integration to users. Prepare and review the full release
instead.

Until then, testers can manually copy `develop/custom_components/meshbeacon` to
`/config/custom_components/meshbeacon` and restart Home Assistant Core. This does not register
the folder as Marketplace-managed, so later updates still need manual copying. Keep the app
installation unchanged: reinstalling it from another repository URL can create a separate
identity and data store.

## Moving a hand-copied integration to the Marketplace

Installing from the Marketplace over an existing `custom_components/meshbeacon/` replaces the folder
(the Marketplace moves the old one aside and puts it back if the install fails). The integration's
set-up, entities and history are stored by Home Assistant, not in that folder, so they stay. The
integration's config entry is upgraded to version 2 on the next start, without changing any entity
ID. **Take a full backup first:** going back to the older integration means restoring that backup,
not installing an older version.

## Not done (maintainer steps)

- A GitHub release (M2, approval).
- A catalog listing in `hacs/default` (decision D14, after the first release). It needs a full
  release and passing HACS action and Hassfest checks, and it is submitted by the maintainer
  (CLAUDE.md rule 10).
