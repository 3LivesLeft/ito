# ito brand identity

**Name:** ito (always lowercase in user-facing copy)  
**Website:** https://ito.earth  
**Tagline:** The internet, reimagined.

ito is a private, decentralised connectivity project built on Reticulum. Its visual language is calm, clear and practical.

## Palette

| Role | Colour |
| --- | --- |
| Mist / background | `#E8F3ED` |
| Sage / accent | `#A6C9B2` |
| Deep green / text | `#284C40` |

The SVG in [logo.svg](logo.svg) is an initial vector interpretation of the thread-and-earth idea. It is **provisional** pending visual review, not a verified reproduction of the earlier approved artwork. Do not replace it with raster exports until the design has been checked at small sizes.

## Assets and usage

- [logo.svg](logo.svg) is the provisional full-size emblem.
- [favicon.svg](favicon.svg) is a simplified 64-unit icon designed to remain legible at small sizes.
- Both are self-contained SVGs with no external fonts, scripts or network resources.
- Use the exact colours above. For text on pale backgrounds, prefer deep green rather than the light sage accent.
- These files are source artwork, not proof that the Home Assistant app or dashboard loads a favicon automatically. Home Assistant's UI controls its own branding; do not claim that placing these files here changes the app icon.
- Do not embed custom JavaScript, external stylesheets or unsupported cards into the example Lovelace dashboard solely to force branding.

## Optional Home Assistant theme

[ito-theme.yaml](../docs/home-assistant/ito-theme.yaml) provides a sage-green theme for Home Assistant's built-in dashboard cards. To use it, add the file under your Home Assistant `themes` directory, ensure `frontend: themes: !include_dir_merge_named themes` is configured in `configuration.yaml`, reload themes (or restart Home Assistant), then select **ito sage** in your user profile's theme settings. Existing theme settings and other dashboards are unaffected until you select the theme. This is optional and does not replace Home Assistant's own logo or app icons.

For a step-by-step upgrade, theme installation and messaging regression checklist, see the [Home Assistant ito setup guide](../docs/home-assistant/ito-brand-setup.md).

## Compatibility

The Home Assistant app slug, integration domain, discovery service, entity IDs, Python package and data directories deliberately remain `meshbeacon`. This is an outward-facing rename, not a data migration. Do not rename identities or message stores as part of branding.

## Tone

Use UK English, short direct sentences, plain language and precise privacy claims. Avoid inflated promises and unnecessary technical jargon. Refer to Reticulum and LXMF by their correct names.
