# ADR 0026: Repository moved to 3LivesLeft/ito; installed apps keep their slug and data

**Status:** Proposed (21 November 2026). **Related:** ADR 0025 (rename to ito, PR #12), ADR 0006
(discovery), ADR 0015 (app store and Marketplace), [v0.3 install research](../research/v0.3-install.md).

## Context

The GitHub repository was renamed from `3LivesLeft/meshbeacon` to `3LivesLeft/ito`. Home Assistant
still showed "MeshBeacon" after a tester removed the old repository and added the new one. An audit
of `main` and `develop` (21 Nov 2026) found three causes:

| Finding | Evidence |
|---|---|
| **[Verified]** Without a `#branch` suffix the Supervisor clones the repository's **default branch**, which is `main`. `main` is still the v0.2.0 merge (`80e9f59`): name MeshBeacon, old URLs | Supervisor `store/git.py` (`branch` is passed to the clone only when set) and `validate.py` (`RE_REPOSITORY`); the default branch is from the GitHub API |
| **[Verified]** The rename itself (PR #12) is **not merged** into `develop`, so `develop` also said MeshBeacon in `repository.yaml`, `config.yaml`, `hacs.json` and the integration's manifest | `git log origin/develop` |
| Every branch pointed `repository.yaml`, `config.yaml`, the manifest's links, the repairs' "learn more" links, the image's source label and the one-click links at the old repository | This audit |

The Supervisor facts that decide what a rename may touch:

| Fact | Evidence |
|---|---|
| **[Verified]** An installed app's slug is the first 8 hex digits of SHA-1 of the lower-cased repository address **as the user typed it**, `#branch` included, then the app's slug: `ce27fbb5_meshbeacon` (old address), `d6f2aa84_meshbeacon` (new address). Each slug has its own data folder, and backups restore only into the same slug | Supervisor `store/utils.py` `get_hash_from_repository`, `store/repository.py`; v0.3 install research |
| **[Verified]** The Supervisor refuses to remove a repository while an app installed from it is installed (no force option) | Supervisor `store/__init__.py` `remove_repository` |
| **[Verified]** GitHub forwards git operations on the old address to the renamed repository; this clone still fetches through it | `git fetch` against `https://github.com/3LivesLeft/meshbeacon`, 21 Nov 2026 |
| **[Assumption]** Home Assistant's Marketplace keeps updating an integration installed under the old repository name, through GitHub's API redirect | Not verified against the Marketplace's code |

## Decision

1. **The name and the links Home Assistant shows follow the rename.** `repository.yaml` (name,
   URL, maintainer), the app's `config.yaml` (name, URL), `hacs.json`, the integration's manifest
   (name, documentation, issue tracker), the repairs' "learn more" links, the image's title and
   source labels, and the one-click links in the guides. The name is **ito**, lower case, as in
   ADR 0025.
2. **The identifiers that key installed data stay `meshbeacon`.** That means the app slug and its
   folder, the discovery service, and the integration domain. Renaming the slug would give every
   installation a new, empty data folder; there is no slug migration and a backup cannot be
   restored into another slug. Renaming the domain would orphan every config entry. The image
   name (`ghcr.io/3livesleft/meshbeacon`) is unpublished and is decided with M2.
3. **Existing installations keep the address they were installed from.** The old address keeps
   its slug, its data and its updates through GitHub's redirect. The guide tells users to change
   nothing, and warns that adding the new address installs a separate app.
4. **New installations use the new address.** The one-click links use `d6f2aa84_meshbeacon`.
5. `tests/unit/test_rename_compatibility.py` freezes the identifiers in point 2, checks that the
   metadata in point 1 says ito and points at the new repository, pins both slugs, and checks
   that the guide's warning is present.

## Consequences

- Home Assistant shows ito only once the change reaches the branch it installs from. That is
  `main` for the plain address, which is a release step (merging `develop` into `main`). Testers
  who add `…/ito#develop` get yet another app (another slug), as for any branch.
- The repairs' "learn more" links point at `blob/main/docs/getting-started.md`, which exists only
  from `develop` onwards, so they resolve once `develop` is released to `main`.
- **[Open]** If someone else ever creates a repository called `3LivesLeft/meshbeacon`, GitHub
  stops redirecting and old installations stop updating. Do not reuse the name. Before the first
  public release, decide whether early testers keep the old address for good, or reinstall from
  the new one and accept a new identity (a backup cannot move data between slugs).
