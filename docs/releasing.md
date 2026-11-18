<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../branding/png/logo-horizontal-dark.png">
  <img src="../branding/png/logo-horizontal-light.png" alt="MeshBeacon" height="48">
</picture>

# Release notes template

**Status:** template only. **No release is approved or published.** Releasing needs the
maintainer's explicit approval and the public release gates in the [roadmap](roadmap.md).

Use this structure so that every release looks and reads the same ([branding](branding.md)).

```markdown
<p align="center"><img src="branding/png/logo-full-light.png" alt="MeshBeacon: Decentralised connectivity for your home" width="480"></p>

# MeshBeacon <version>

**Decentralised connectivity for your home.**

## Highlights
- One line per user-visible change, in plain UK English.

## Upgrading
- What the user must do (ideally nothing), and how long it takes.

## Privacy and security
- Any change to what is collected, shown, stored or exposed. "None" is a valid answer.

## Resources
- Memory and CPU on the reference Raspberry Pi, compared with the previous release.

## Known issues

## Thanks and provenance
- Contributors; AI assistance disclosed as in CONTRIBUTING.md.
```

**Checklist before publishing (with approval):**
- [ ] Logo, name and tagline as in [branding](branding.md); no cropped or recoloured artwork.
- [ ] `tools/brand/build.py --check` passes; the app's `icon.png` and `logo.png` are current.
- [ ] Screenshots taken from `tools/panel_preview.html` (or the real interface), in light and dark themes.
- [ ] No images hot-linked from external hosts in the notes.
- [ ] Accessibility checks re-run if the interface changed.
