<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../branding/png/logo-horizontal-dark.png">
  <img src="../branding/png/logo-horizontal-light.png" alt="MeshBeacon" height="48">
</picture>

# Getting started with MeshBeacon (v0.2, testing)

**Decentralised connectivity for your home.**

> **Status: for testers.** MeshBeacon is experimental and not published. These steps install the
> development version as a local app. No terminal and no YAML are needed.

## What you get

- **The MeshBeacon app:** a private Reticulum node on your Home Assistant device.
- **Optional: MeshBeacon in your sidebar.** Its own page shows connectivity, figures, history and
  peers, and entities are available for dashboards and automations. Today this needs the
  MeshBeacon integration (part 2). A built-in page that needs no integration is a goal: see
  [why it is not there yet](research/secure-interface-options.md).

## 1. Install the app (about 5 minutes)

Follow [installing the local prototype](install-local-prototype.md): copy the `meshbeacon` folder
to your Home Assistant, install it from the app store, choose a peer in the **Configuration**
tab, and start it. The app log then says "Connected to … Your node is online."

## 2. Add MeshBeacon to the sidebar (about 5 minutes, optional)

1. **Copy the integration.** Install the **File editor** app (or **Samba share**). Create the
   folder `/config/custom_components/meshbeacon` and put the files from this repository's
   `custom_components/meshbeacon` folder in it (keep the `brand`, `frontend` and `translations`
   folders).
2. **Restart Home Assistant:** Settings → System → Restart.
3. **Switch it on in the app:** MeshBeacon → Configuration → **Show MeshBeacon's status in Home
   Assistant** → Save, then restart the app.
4. **Add it:** Settings → Devices & services shows **MeshBeacon discovered**. Choose **Add**.

**MeshBeacon** now appears in the sidebar, with a lighthouse icon, for administrators. It follows
your light or dark theme and works on phones, tablets and computers.

- There is nothing else to configure: no keys, no dashboards.
- Removing it is the same steps in reverse. See the
  [integration guide](home-assistant-integration.md#set-up).
- Privacy: everything stays on your Home Assistant device; see the
  [integration guide](home-assistant-integration.md#privacy-and-security).

## Help

- The app log explains each state in plain words. In the panel, **Diagnostics** shows versions,
  start times and restarts.
- [Troubleshooting in the app's documentation](../meshbeacon/DOCS.md).
