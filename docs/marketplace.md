<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../branding/png/logo-horizontal-dark.png">
  <img src="../branding/png/logo-horizontal-light.png" alt="MeshBeacon" height="48">
</picture>

# The integration in Home Assistant's Marketplace

**Status:** the repository is **compatible** with the Marketplace built into Home Assistant
2026.11 and newer (the successor of HACS). **Nothing is published or listed:** the first GitHub
release, and any catalog listing, need the maintainer's approval ([releasing](releasing.md)).
Facts and sources: [v0.3 installation research](research/v0.3-install.md).

## What the Marketplace reads from this repository

| Item | Where | Checked by |
|---|---|---|
| `hacs.json` | repository root (and every release tag) | `tools/check_release.py`, `tests/unit/test_hacs.py` |
| Keys | `name` and `homeassistant` (`2026.11.0`) only; no ZIP release, no content in root | same |
| The integration | `custom_components/meshbeacon/` with `manifest.json`, `brand/` and the panel files in `frontend/` | same |
| The app store files | `repository.yaml` and `meshbeacon/` sit beside it; the Marketplace installs the integration and ignores them | `tools/check_release.py` |

## How users get it (from the first release)

1. In the MeshBeacon app's **Documentation** tab, or the README, select **Add the MeshBeacon
   dashboard** (My link `marketplace_repository`, owner `3LivesLeft`, repository `meshbeacon`,
   category `integration`).
2. Until MeshBeacon is in the catalog, the Marketplace first asks to **connect GitHub** (a code to
   enter at github.com; read-only, public data only) and to confirm adding the repository.
3. The first time only, accept the Marketplace's warning.
4. **Install**, then follow the setup page or the restart repair.

Updates then appear under **Settings → Updates**. After an integration update, Home Assistant asks
for a restart through a repair.

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
