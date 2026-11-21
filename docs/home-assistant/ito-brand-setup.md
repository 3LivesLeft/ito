# Use the ito identity in Home Assistant

ito is the new name of the MeshBeacon Home Assistant app and integration ([ADR 0025](../adr/0025-rename-to-ito.md)). Updating in place renames what you see: the app, the integration, the sidebar panel, its messages and the icons. It does not rename internal components or touch Reticulum or LXMF data. This guide covers the update, the optional sage theme and a check that nothing else changed.

## Before upgrading

1. Back up your Home Assistant configuration and the app's persistent data using the normal Home Assistant backup workflow.
2. Confirm that messaging works before the upgrade, and record the existing identity/destination in your messaging client.
3. Do **not** uninstall the old app to perform the rename: uninstalling may remove its persistent data. Install an updated version in place, using the existing `meshbeacon` slug.
4. Keep `custom_components/meshbeacon` at the same path. The display name is now ito, but the integration domain stays `meshbeacon`, and your existing entity IDs (`sensor.meshbeacon_…`) stay as they are. Only a new installation gets `sensor.ito_…` IDs.

## Optional sage theme

1. Copy [ito-theme.yaml](ito-theme.yaml) to `/config/themes/ito-theme.yaml` in Home Assistant.
2. Ensure the following is present in `/config/configuration.yaml` (merge it with an existing `frontend:` section rather than duplicating that key):

   ```yaml
   frontend:
     themes: !include_dir_merge_named themes
   ```

3. Validate the configuration, reload themes or restart Home Assistant, then select **ito sage** in your Home Assistant user profile.
4. Import [dashboard.yaml](dashboard.yaml) through the dashboard raw configuration editor. The example uses the `ito_` entity IDs of a new installation; if yours start with `meshbeacon_`, replace `.ito_` with `.meshbeacon_` first (the file's header explains).

The theme is **optional and user-selected**. It can affect other dashboards for the user who selects it. ito's own panel already uses the ito colours, with or without it.

## Visual assets

The provisional ito artwork reaches Home Assistant only through its supported mechanisms ([branding §5](../branding.md#5-iconography)): the app's `icon.png` and `logo.png` (app store and app page), the integration's local brand images (Settings → Devices & services), and `mdi:earth` in the sidebar. The app store may show the new icon only after **Check for updates**. Nothing overwrites Home Assistant's own favicon or system assets. Source SVGs are in [`branding/`](../../branding/), generated from the masters in `branding/src/`.

## Regression checklist

- Existing app upgrades in place; its slug remains `meshbeacon`.
- Existing integration and entities load; no duplicate integration is created.
- Reticulum node identity/destination remains identical after restart.
- Existing LXMF conversations and messages remain available.
- Send a message, receive a reply, and confirm both appear in the dashboard or messaging client.
- The app store, app page, Devices & services and the sidebar show ito and the globe artwork.
- The device is called ito; existing entity IDs still start with `meshbeacon_`.
- Test the panel and the theme in light and dark contexts, mobile and desktop; check text contrast.
- Check the app logs for new storage, authentication or messaging errors.

If any identity, storage or messaging check fails, stop and restore from backup rather than deleting/reinstalling the app.

**Status:** This is a manual verification plan, not evidence that the checks have passed. No live Home Assistant installation has been tested by this documentation change.
