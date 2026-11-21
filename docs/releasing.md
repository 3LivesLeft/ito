<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../branding/png/logo-horizontal-dark.png">
  <img src="../branding/png/logo-horizontal-light.png" alt="ito" height="48">
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

**Pre-built images are the recommended public route.** On-device builds from the repository (no
`image:` key yet) are for development and early testers only (decision A-4); `config.yaml` gains
`image:` in the release that first publishes images, never before the images exist.

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
5. **Pinned inputs** (M1.2): the base image, the Dockerfile frontend (`# syntax=`), BuildKit, the
   SBOM scanner and QEMU's binfmt image by digest; Python packages by hash, for the app **and** for
   every CI and release tool (`requirements-*.txt`, compiled from `requirements-*.in`); actions by
   commit SHA. Release builds use no action cache. `tests/unit/test_hacs.py` enforces all of this.
6. **Promote, never rebuild** (M1.2): publishing pushes the exact OCI archive the dry run verified
   (`candidate-1.tar`) and checks what the registry then serves against the recorded
   `digests.json`: the **image index, every platform manifest and every attestation manifest**
   (SBOM, provenance) must match exactly. A publishing job must not build;
   `tests/unit/test_publishing_guards.py` (`promotion_problems`) enforces this for any job with
   `packages: write`, and only a workflow named in its `PUBLISHING_WORKFLOWS` list (empty until M2
   is approved) may hold any write permission. Every other workflow stays exactly `contents: read`.
7. **Never delete or move a published tag or image.** Restoring an app backup pulls that version's
   image again, and the Marketplace lists earlier releases.
8. **The release commit's changelog entry has a date**, not "unreleased" (the check refuses it).
9. **A change to `apparmor.txt` needs a new version** [Verified, Supervisor
   `supervisor/apps/app.py` on `main`, 20 Nov 2026: `install()` and `update()` call
   `install_apparmor()`, `rebuild()` does not, and a rebuild is refused unless the installed and
   store versions match]. Without one, Home Assistant offers only *Rebuild*, which builds the new
   image but keeps enforcing the old profile (0.3.1: the RPC key folder of ADR 0023 was denied on
   the Pi). The same applies to development installs from `develop`.

## 3. Steps (from M2, with approval)

| # | Step | Tooling | Status |
|---|---|---|---|
| 1 | Bump the version in the six places; date the changelog; run all CI on the branch | `tools/check_release.py` | Ready |
| 2 | Tag `vX.Y.Z` (signed tag) on the release commit; do not move `main` yet | git | Ready |
| 3 | **Dry run on the tag:** build both architectures twice from scratch with `SOURCE_DATE_EPOCH` = commit time and rewritten timestamps; verify platforms, labels, SBOM (SPDX) and provenance attestations, and that both builds give **identical image digests**; record the complete set (`--write-digests digests.json`: index, platform manifests, attestations); vulnerability scans of **each platform explicitly** (amd64 and arm64; any critical finding fails; a high finding with a fix available fails) | `.github/workflows/release-dry-run.yaml`, `tools/verify_image.py` | Ready (M1, M1.2) |
| 4 | **Publish the verified archive** to GHCR as a multi-arch image, without rebuilding: for example `skopeo copy --all --preserve-digests oci-archive:candidate-1.tar docker://ghcr.io/…:X.Y.Z`, in the same workflow run as step 3 (the archive never leaves that run) | Publishing job with `packages: write`, behind a protected `release` environment that needs the maintainer's approval; must not build (rule 6) | **M2, not written yet** |
| 5 | **Sign** the pushed digests with cosign (keyless, GitHub OIDC), and attach the SBOM and provenance. Keyless signing records the signature in the public Rekor transparency log | cosign, pinned | **M2** |
| 6 | **Verify what was published:** pull by tag into an OCI archive and run `tools/verify_image.py pulled.tar --version X.Y.Z --expect-digests digests.json`; verify the signature against this repository's workflow identity | `cosign verify`, `tools/verify_image.py` | **M2** (the digest check is ready) |
| 7 | Record the digests in the release notes; create the GitHub release (stable, not pre-release, unless it is a release candidate) | release notes template below | **M2** |
| 8 | Fast-forward `main` to the tag; the app store and the Marketplace now offer it | git | **M2** |
| 9 | Install it in the isolated VM from both stores, as a new user would (acceptance IN-1 to IN-11) | VM | **M2** |

**Decided (M1.2):** step 4 promotes the dry run's archive; it does not use Home Assistant's builder
actions or any second build. That is the only way to guarantee that what is published is what was
verified.

### Reproducibility: what it does and does not show

| Claim | Status |
|---|---|
| Two builds of one commit, on one runner, minutes apart, give identical image digests | **Verified** in every dry run |
| A rebuild on another day, or by someone else, gives the same digests | **Not expected.** The `apk add --upgrade` security layer installs whatever Alpine serves that day (minimum versions only), and Alpine replaces package files in place. The layer goes once the base image carries the fixes; then only digest-pinned images and hash-pinned wheels remain |
| Every image and package the build reads is pinned | **Verified**, except the Alpine packages above and the runner's own `docker buildx` client (the action uses the runner's copy) |
| SBOM and provenance describe the published image | **Yes, by construction** under rule 6: they are produced in the verified build and pushed with it |

Promotion (rule 6) makes cross-day reproducibility unnecessary for integrity: the published bytes
are the verified bytes. Independent rebuilds remain a useful check for reviewers once the apk layer
is gone.

The Supervisor does not verify signatures (it has no signing support today). Signatures and SBOMs
are for users and reviewers, and for ito's own verification in step 6.

## 4. Rollback

| Part | How | Notes |
|---|---|---|
| App | Restore the backup taken before the update (Settings → System → Backups, the app only) | Pulls the old image tag again (rule 6). The node identity in the backup is restored with it |
| Integration | Restore the Home Assistant backup taken before the update | The Marketplace documentation says so; an older integration cannot load a newer config entry |
| A bad release | Publish a fixed patch release; never delete the bad tag | The repair texts point users to **Settings → Updates** |

## 5. Release notes template

Use this structure so that every release looks and reads the same ([branding](branding.md)).

```markdown
<p align="center"><img src="branding/png/logo-full-light.png" alt="ito: The internet, reimagined" width="480"></p>

# ito <version>

**The internet, reimagined.**

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
- [ ] Repository settings (a test cannot check these): a protected `release` environment with the
      maintainer as required reviewer; tag protection for `v*`; Actions' default token read-only.
- [ ] The publishing job promotes `candidate-1.tar` from the same run and checks `--expect-digests`
      (rule 6); `tests/unit/test_publishing_guards.py` passes with the new workflow.
- [ ] `tools/check_release.py --ref <tag> --tag <tag>` passes; the release dry run is green on the tag.
- [ ] Logo, name and tagline as in [branding](branding.md); no cropped or recoloured artwork.
- [ ] `tools/brand/build.py --check` passes; the app's `icon.png` and `logo.png` are current.
- [ ] Screenshots taken from `tools/panel_preview.html` (or the real interface), in light and dark themes.
- [ ] No images hot-linked from external hosts in the notes.
- [ ] Accessibility checks re-run if the interface changed.
