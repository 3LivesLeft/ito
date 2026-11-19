<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../branding/png/logo-horizontal-dark.png">
  <img src="../branding/png/logo-horizontal-light.png" alt="MeshBeacon" height="48">
</picture>

# Releasing

**Status:** process defined and dry-run tested (M1). **No release is approved or published.**
Publishing needs the maintainer's explicit approval (decision D3, milestone M2) and the public
release gates in the [roadmap](roadmap.md). Background: [ADR 0015](adr/0015-distribution-and-updates.md).

## 1. What a release is

One version number, **one git tag** `vX.Y.Z`, for both parts in this one repository:

| Part | Users get it from | Reads |
|---|---|---|
| App | Home Assistant's app store (this repository as a custom app repository) | `meshbeacon/config.yaml` on the **default branch**, then the image `ghcr.io/3livesleft/meshbeacon:X.Y.Z` |
| Integration | Home Assistant's Marketplace | the newest **GitHub release** (its tag's `hacs.json` and `custom_components/meshbeacon/`) |

Identifiers (name, slug, repository, image) live in `project.yaml`; a rename before the first
release starts there.

## 2. Rules

1. **`main` carries releases only** (D11). The app store offers a new version as soon as
   `config.yaml` on `main` changes, so nothing reaches `main` before its image exists.
2. **Order:** build and push the images for the tag → verify them → create the GitHub release →
   fast-forward `main` to the tag. Never the other way round.
3. **One version everywhere:** `config.yaml`, `manifest.json`, the core's `__version__`, the
   Dockerfile's `BUILD_VERSION` default, the changelog's top entry and the tag.
   `python tools/check_release.py --ref vX.Y.Z --tag vX.Y.Z` must pass.
4. **Compatibility:** integration N works with app N and N−1 (`compatibility.py`). A release that
   breaks that, or the status schema, needs a new major schema and the Supervisor's
   `breaking_versions` entry.
5. **Pinned inputs:** the base image by digest (as now), Python packages by hash, actions by commit
   SHA.
6. **Never delete or move a published tag or image.** Restoring an app backup pulls that version's
   image again, and the Marketplace lists earlier releases.
7. **The release commit's changelog entry has a date**, not "unreleased" (the check refuses it).

## 3. Steps (from M2, with approval)

| # | Step | Tooling | Status |
|---|---|---|---|
| 1 | Bump the version in the six places; date the changelog; run all CI on the branch | `tools/check_release.py` | Ready |
| 2 | Tag `vX.Y.Z` (signed tag) on the release commit; do not move `main` yet | git | Ready |
| 3 | **Dry run on the tag:** build both architectures twice from scratch with `SOURCE_DATE_EPOCH` = commit time and rewritten timestamps; verify platforms, labels, SBOM (SPDX) and provenance attestations, and that both builds give **identical image digests** | `.github/workflows/release-dry-run.yaml`, `tools/verify_image.py` | Ready (M1) |
| 4 | **Publish the images** to GHCR from the verified build, as a multi-arch manifest | Publishing workflow with `packages: write`, behind a protected `release` environment that needs the maintainer's approval | **M2, not written yet** |
| 5 | **Sign** the pushed digests with cosign (keyless, GitHub OIDC), and attach the SBOM and provenance. Keyless signing records the signature in the public Rekor transparency log | cosign, pinned | **M2** |
| 6 | **Verify what was published:** pull by tag, check that the tag resolves to the digests from step 3, verify the signature against this repository's workflow identity | `cosign verify`, `tools/verify_image.py` | **M2** |
| 7 | Record the digests in the release notes; create the GitHub release (stable, not pre-release, unless it is a release candidate) | release notes template below | **M2** |
| 8 | Fast-forward `main` to the tag; the app store and the Marketplace now offer it | git | **M2** |
| 9 | Install it in the isolated VM from both stores, as a new user would (acceptance IN-1 to IN-11) | VM | **M2** |

**[Open]** whether step 4 uses Home Assistant's builder actions (their documented path) or the same
`docker buildx` invocation as the dry run. Using the dry run's exact command keeps the verified
digests identical to the published ones; that is the recommendation, decided at M2.

The Supervisor does not verify signatures (it has no signing support today). Signatures and SBOMs
are for users and reviewers, and for MeshBeacon's own verification in step 6.

## 4. Rollback

| Part | How | Notes |
|---|---|---|
| App | Restore the backup taken before the update (Settings → System → Backups, the app only) | Pulls the old image tag again (rule 6). The node identity in the backup is restored with it |
| Integration | Restore the Home Assistant backup taken before the update | The Marketplace documentation says so; an older integration cannot load a newer config entry |
| A bad release | Publish a fixed patch release; never delete the bad tag | The repair texts point users to **Settings → Updates** |

## 5. Release notes template

Use this structure so that every release looks and reads the same ([branding](branding.md)).

```markdown
<p align="center"><img src="branding/png/logo-full-light.png" alt="MeshBeacon: Decentralised connectivity for your home" width="480"></p>

# MeshBeacon <version>

**Decentralised connectivity for your home.**

## Highlights
- One line per user-visible change, in plain UK English.

## Upgrading
- What the user must do (ideally nothing), and how long it takes. Which part to update first.

## Privacy and security
- Any change to what is collected, shown, stored or exposed. "None" is a valid answer.

## Resources
- Memory and CPU on the reference Raspberry Pi, compared with the previous release.

## Verification
- Image digests (linux/amd64, linux/arm64), from the dry run and confirmed after publishing.
- How to verify the signature (`cosign verify`, identity and issuer).

## Known issues

## Thanks and provenance
- Contributors; AI assistance disclosed as in CONTRIBUTING.md.
```

**Checklist before publishing (with approval):**
- [ ] `tools/check_release.py --ref <tag> --tag <tag>` passes; the release dry run is green on the tag.
- [ ] Logo, name and tagline as in [branding](branding.md); no cropped or recoloured artwork.
- [ ] `tools/brand/build.py --check` passes; the app's `icon.png` and `logo.png` are current.
- [ ] Screenshots taken from `tools/panel_preview.html` (or the real interface), in light and dark themes.
- [ ] No images hot-linked from external hosts in the notes.
- [ ] Accessibility checks re-run if the interface changed.
