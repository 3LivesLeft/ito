# Use the ito identity in Home Assistant

ito is the user-facing name of the existing `meshbeacon` Home Assistant app and integration. This guide applies the optional visual identity without renaming internal components or touching Reticulum/LXMF data.

## Before upgrading

1. Back up your Home Assistant configuration and the app's persistent data using the normal Home Assistant backup workflow.
2. Confirm that messaging works before the upgrade, and record the existing identity/destination in your messaging client.
3. Do **not** uninstall the old app to perform the rename: uninstalling may remove its persistent data. Install an updated version in place, using the existing `meshbeacon` slug.
4. Keep `custom_components/meshbeacon` at the same path. The display name is now ito, but the integration domain and entity IDs remain unchanged.

## Optional sage theme

1. Copy [ito-theme.yaml](ito-theme.yaml) to `/config/themes/ito-theme.yaml` in Home Assistant.
2. Ensure the following is present in `/config/configuration.yaml` (merge it with an existing `frontend:` section rather than duplicating that key):

   ```yaml
   frontend:
     themes: !include_dir_merge_named themes
   ```

3. Validate the configuration, reload themes or restart Home Assistant, then select **ito sage** in your Home Assistant user profile.
4. Import [dashboard.yaml](dashboard.yaml) through the dashboard raw configuration editor. The example expects the existing `meshbeacon` entity IDs; update any that differ in your installation.

The theme is **optional and user-selected**. It can affect other dashboards for the user who selects it. It does not automatically replace Home Assistant's app icon, sidebar icon, browser favicon, or dashboard branding.

## Visual assets

The provisional [ito logo](../../brand/logo.svg) and [small icon](../../brand/favicon.svg) are available as source SVGs. They are not automatically loaded by Home Assistant. Avoid overwriting Home Assistant's global favicon or system assets. An app-specific icon should only be added using a supported Home Assistant app repository mechanism, with a verified raster export and visual review.

## Regression checklist

- Existing app upgrades in place; its slug remains `meshbeacon`.
- Existing integration and entities load; no duplicate integration is created.
- Reticulum node identity/destination remains identical after restart.
- Existing LXMF conversations and messages remain available.
- Send a message, receive a reply, and confirm both appear in the dashboard or messaging client.
- Test the theme in light and dark contexts, mobile and desktop; check text contrast.
- Check the app logs for new storage, authentication or messaging errors.

If any identity, storage or messaging check fails, stop and restore from backup rather than deleting/reinstalling the app.

**Status:** This is a manual verification plan, not evidence that the checks have passed. No live Home Assistant installation has been tested by this documentation change.
