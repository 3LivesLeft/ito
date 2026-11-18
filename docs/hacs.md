# HACS compatibility (prepared, not published)

**Status:** the repository is *prepared* so that HACS (the Home Assistant Community Store) could
install the integration. **Nothing is published or promoted.** There is no release-installation
workflow, no "add to HACS" button or badge, and no submission to the HACS default list. This
follows the maintainer's decision of 18 Nov 2026: approve preparation, but do not publish,
promote or enable an official release-installation workflow yet.

## What is in place

| Item | Where | Notes |
|---|---|---|
| `hacs.json` | repository root | `name`, `homeassistant` (minimum **2026.10.4**, the release the test harness runs) and `render_readme`. No `zip_release`, no `filename`, no `content_in_root` |
| One integration | `custom_components/meshbeacon/` | HACS copies only this folder. The sidebar panel's files are inside it (`frontend/`), so they arrive with it |
| Manifest | `custom_components/meshbeacon/manifest.json` | `domain`, `name`, `version`, `documentation`, `issue_tracker` and `codeowners` are set; `requirements` is empty, so nothing is installed from PyPI |
| Offline checks | `tests/unit/test_hacs.py` | Known `hacs.json` keys only; no release ZIP or release workflow; exactly one integration; manifest fields; integration and app versions equal; minimum HA version equals the tested harness; panel files inside the integration |

The repository also remains a Home Assistant **app** repository (`repository.yaml`, `meshbeacon/`).
The two do not interfere: the Supervisor reads `repository.yaml`, and HACS reads `hacs.json` and
`custom_components/`.

## What HACS would install today

**[Assumption]** (HACS's documented behaviour, not checked against a live HACS in this
session): when a repository has no GitHub releases, HACS offers the **default branch**. `main` does not
contain the integration until PR #3 is merged, so adding the repository to HACS today installs
nothing usable. After a merge, anyone who adds the repository's URL as a **custom repository**
could install the integration from `main`. That is technically possible without any action by the
project. It is the "install source" consequence the maintainer was asked about. It is not
advertised anywhere.

## Before any HACS listing (maintainer decisions and steps)

These are deliberately not done:

1. **Decide** whether HACS is an official install path. If it is, document it as the first step of
   [the integration guide](home-assistant-integration.md#set-up), instead of copying the folder.
2. **Releases:** decide whether HACS should follow tagged releases (recommended, so users get
   reviewed versions rather than every commit on `main`). That requires publishing releases, which
   is not approved.
3. **HACS validation action:** run HACS's own validation (`hacs/action`, category `integration`).
   It needs GitHub API access, a repository description, topics and issues enabled. Pin it by
   commit SHA like the other actions in CI.
4. **Brand images:** HACS's default list expects brand images (icon and logo). Adding them to Home
   Assistant's brands repository is a contribution to an Open Home Foundation project. The project
   rules forbid AI agents from making it ([CLAUDE.md](../CLAUDE.md) rule 10), so a human must
   decide and make it.
5. **Default list:** a submission to the HACS default repository list is a separate,
   public step.

## Installing through HACS as a custom repository (for testing only, after merge)

For the maintainer's own testing. This is not to be published as user documentation until step 1
above is decided.

1. HACS → ⋮ → **Custom repositories** → add the repository URL, category **Integration**.
2. Install **MeshBeacon**, then restart Home Assistant.
3. In the MeshBeacon app, switch on "Show MeshBeacon's status in Home Assistant" and restart the
   app. Home Assistant then offers MeshBeacon under Settings → Devices & services.
