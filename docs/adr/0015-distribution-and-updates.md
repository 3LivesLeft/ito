# ADR 0015: Distribution through the app store and the Marketplace

- **Status:** **Accepted** (maintainer, 19 Nov 2026: decisions D1, D2, D4, D11; D3 in principle).
  Implemented as milestone M1 on `feature/v0.3.0-install-ready`. **Nothing is published:** images
  and releases follow at M2, after approval.
- **Date:** 19 November 2026
- **Evidence:** [v0.3 installation research](../research/v0.3-install.md)

## Context

Installing MeshBeacon meant copying folders into Home Assistant by hand. Ordinary users must be
able to install and update it through Home Assistant's interface, with no terminal or file
copying, without new privileges. No supported mechanism lets an app install its own integration,
and writing into Home Assistant's configuration directory is excluded (architecture §8).

## Decision

1. **Two guided stages, both in Home Assistant's own interface:**
   - **The app** comes from this repository as a custom app repository (`repository.yaml`), opened
     with a My link (`supervisor_app?app=<store slug>&repository_url=<repository>`). From M2 the
     app store pulls a pre-built, multi-arch image (`image:` in `config.yaml`).
   - **The integration** comes from the built-in Marketplace (Home Assistant 2026.11+), which reads
     `hacs.json` and `custom_components/meshbeacon/` from the same repository (`marketplace_repository`
     My link).
2. **One repository, one version, one tag** for the app and the integration
   ([releasing](../releasing.md)). The integration accepts the app's version and the previous
   minor version, and raises a repair naming which part to update otherwise.
3. **Minimum Home Assistant 2026.11.0**, the first release with the Marketplace.
4. **`main` carries releases only.** The app store reads `config.yaml` from the default branch, so
   a version on `main` is offered to users immediately; the Marketplace follows GitHub releases.
   Release order: images, then the GitHub release, then `main`.
5. **The node's identity in Home Assistant is independent of the app's slug** (config entry v2,
   `node_key`), so a later move from the local app to the published app keeps entity IDs and
   history (migration itself is ADR 0016, planned for M6; not part of M1).
6. **Project identifiers in one place** (`project.yaml`), checked against every copy by tests, so
   the name decided before the first release is a small change.

## Consequences

- Rating unchanged (8). No new `config.yaml` privileges; `tools/check_release.py` refuses them.
- Adding a repository that is not in the Marketplace catalog needs the user to connect a GitHub
  account (read-only, device sign-in). A catalog listing removes that step (D14, after the first
  release, made by the maintainer).
- The Supervisor does not verify image signatures. Cosign signatures and SBOMs are evidence for
  users and reviewers, not something the Supervisor checks.
- Rollback of the integration is a backup restore, as the Marketplace documentation says; image
  tags are never deleted, so an app backup can always be restored.

## Rejected

App writes the integration into `/config`; app gains `homeassistant_api`; integration installs the
app through Home Assistant's internal `AddonManager`; Ingress (ADR 0013, blocked). Reasons in the
[research](../research/v0.3-install.md).
