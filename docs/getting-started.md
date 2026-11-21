<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../branding/png/logo-horizontal-dark.png">
  <img src="../branding/png/logo-horizontal-light.png" alt="MeshBeacon" height="48">
</picture>

# Getting started with MeshBeacon

**Decentralised connectivity for your home.**

> **Status: prepared for the first release (v0.3.0), not yet available.** The buttons below work
> once MeshBeacon's first release is published, with pre-built images: that is the recommended way
> to install it. Until then, see [early testers](#early-testers-before-the-first-release).

You need **Home Assistant OS 2026.11 or newer** (or a supervised installation), and an
administrator account. No terminal, no YAML and no copying of files.

## What you get

- **The MeshBeacon app:** a private Reticulum node on your Home Assistant device.
- **The MeshBeacon dashboard (optional, recommended):** its own page in the sidebar with
  connectivity, figures, history and peers, plus entities for your own dashboards and
  automations. It comes as a separate part, the MeshBeacon integration, from Home Assistant's
  Marketplace.

## 1. Install the app (about 3 minutes)

1. Select this button, or open the link on a device signed in to your Home Assistant:

   [Open MeshBeacon in your Home Assistant](https://my.home-assistant.io/redirect/supervisor_app/?app=ce27fbb5_meshbeacon&repository_url=https://github.com/3LivesLeft/meshbeacon)

   Home Assistant asks whether to add the MeshBeacon app repository. Choose **Add**.
2. On the MeshBeacon page, select **Install**. Home Assistant downloads the app (about a minute
   on a Raspberry Pi 4).
3. Open **Configuration**: add a peer you trust (optional; without one MeshBeacon makes no
   connections), and switch on **Show MeshBeacon's status in Home Assistant** if you want the
   dashboard. Select **Save**.
4. Open **Info** and select **Start**. The **Log** tab explains what MeshBeacon is doing in plain
   words.

## 2. Add the MeshBeacon dashboard

1. Select this button (it is also in the app's **Documentation** tab):

   [Open MeshBeacon in the Marketplace](https://my.home-assistant.io/redirect/marketplace_repository/?owner=3LivesLeft&repository=meshbeacon&category=integration)

2. Until MeshBeacon is listed in the Marketplace's catalog, Home Assistant first asks you to
   **connect GitHub**: it shows a code, you enter it at github.com and approve. The connection
   only reads public information. Then confirm adding the repository.
3. The first time you use the Marketplace, read and accept its warning.
4. Select **Install**. If Home Assistant asks for a restart, use the repair it shows.
5. A notification says **New device discovered: MeshBeacon**. Select it, then **Add**.

**MeshBeacon** now appears in the sidebar, with a lighthouse icon, for administrators. It follows
your light or dark theme and works on phones, tablets and computers.

## Messages (0.4.0 and later)

With **Enable LXMF messaging** on, the dashboard's **Messages** tab lets you read and answer LXMF
messages, for example from Ratspeak or Sideband: copy MeshBeacon's address into your app, add your
app's address with **Add contact**, and message each other. Details:
[Messages](home-assistant-integration.md#messages).

## Updating

The app and the dashboard update separately, both under **Settings → Updates**:

- **MeshBeacon app**: select it and **Update** (not Rebuild). Your node's identity, messaging
  identity, contacts, conversations, peers and settings are kept. Always update the installed app
  in place: adding the repository again with a different branch (`…#branch`) installs a
  **separate** app with a new identity.
- **MeshBeacon** (from the Marketplace): select it and **Update**, then restart Home Assistant
  when the repair asks.

If one is much newer than the other, a repair under **Settings → System → Repairs** says which one
to update. Take a backup before updating if you want to be able to go back: restoring that backup
is the way to return to an earlier version.

## Removing

- **The dashboard:** Settings → Devices & services → MeshBeacon → **Delete**. Home Assistant then
  offers to uninstall it from the Marketplace.
- **The app:** Settings → Apps → MeshBeacon → **Uninstall**. This deletes the node's identity
  unless you keep a backup.

## Early testers (before the first release)

**For development and early testing only** (maintainer decision A-4, 19 Nov 2026). Until images are
published, the app store can still install MeshBeacon from this repository by **building it on your
device**: the same steps as above, but step 2 takes several minutes on a Raspberry Pi 4, needs
internet access for the build, and is more likely to fail. Use a test installation, not one you
depend on. To try an unreleased branch, add the repository as
`https://github.com/3LivesLeft/meshbeacon#<branch>`: the app store treats it as a **different app,
with its own data and identity**, so it never touches an installation from the main repository. The
older [local prototype guide](install-local-prototype.md) (copying the folder) still works.

## Privacy

Everything stays on your Home Assistant device. MeshBeacon connects only to the peers you choose,
and the dashboard reads only your own Home Assistant. See the
[integration guide](home-assistant-integration.md#privacy-and-security).

## Help

- The app log explains each state in plain words. In the dashboard, **Diagnostics** shows
  versions, start times and restarts.
- [Troubleshooting in the app's documentation](../meshbeacon/DOCS.md).
- Already running the local prototype? Keep it for now: moving its identity to the published app
  is planned separately (it must not lose your node's identity), and you will be told how.
