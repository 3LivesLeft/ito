# Getting started with ito

Use Home Assistant OS with **Supervisor 2026.11 or newer** and an administrator account.

The ito app includes its dashboard, setup and messaging. You do not need a Marketplace integration
for normal use. These instructions apply to **0.5.0 onwards**; availability depends on the version
in the branch you install. No release is published by this change.

## Install and start

1. In Home Assistant, open **Settings → Apps → App store → Repositories** and add
   `https://github.com/3LivesLeft/ito`.
2. Select **ito**, then **Install** and **Start**. Local image builds can take several minutes.
3. Open **ito** in the sidebar, or select **Open Web UI** on the app page.
4. In **Settings**, choose a public network or add your own connection. Switch on messaging if
   you want to send and receive messages. Select **Save and apply**.

ito saves your choices, restarts and reconnects the dashboard automatically. There is no YAML,
file copying or Devices & services configuration. Nothing connects externally until you choose
a network or add a peer. The sidebar entry is added on first start; if you later hide it, use
**Show in sidebar** on the app page to bring it back. Access requires a Home Assistant administrator.

## Daily use

**Overview** shows connections and recent charts. **Messages** manages contacts and conversations.
**Diagnostics** shows detailed readings. **Settings** manages your connections, messaging and
advanced options. Use the Light/Dark button to change the dashboard theme.

## Updating

Update the **installed ito app** from **Settings → Updates**. The dashboard, logo, fonts and app
update together. An open dashboard refreshes automatically; while editing settings or keeping a
message draft it offers **Load update** so you can finish first. Existing identities, contacts,
messages and configuration stay in place. Never uninstall to update, and do not add a different
branch URL to update an existing app: that installs a separate app with separate storage.

Recent dashboard charts restart with the app. Home Assistant recorder history is unaffected.

## Optional: Home Assistant entities and automations

Only install the Marketplace integration if you want entities, automations or long-term recorder
history. Install ito from Marketplace, restart Home Assistant if asked, then enable **Share status
with the optional Home Assistant integration** in **ito → Settings** and **Save and apply**.
Under **Settings → Devices & services**, accept the discovered ito entry. The integration's
retained recorder panel is called **ito history** when used with app 0.5.0 or newer.

If you already installed the integration, keep it and its entities. Update it once to get the
clearer panel label and setup guidance. An older installed integration can still show its old
sidebar panel until that update; use the new app's **Open Web UI** for the bundled dashboard.
Marketplace integration updates remain separate and are unnecessary for ordinary dashboard use.

### The repository has moved (installed before 21 Nov 2026?)

The project's repository is now `https://github.com/3LivesLeft/ito` (it was
`https://github.com/3LivesLeft/meshbeacon`). **If you already have the app, change nothing**: keep the
repository you added. GitHub forwards the old address to the new one, so updates keep arriving, and
the app keeps its identity, contacts, conversations and settings. Its name in Home Assistant changes
to ito with the update that renames it.

Do **not** remove the old repository and add the new address to "switch over". Home Assistant
identifies an app by the exact address it was installed from, so the new address installs a
**second, separate app** with a new, empty identity, and uninstalling the old one deletes its data.
Home Assistant will not let you remove a repository while an app from it is installed. If you
already uninstalled the old app, its identity survives only in a Home Assistant backup taken
before that; a backup restores into the old app, never into the new one.

## Removing

- **The dashboard:** Settings → Devices & services → ito → **Delete**. Home Assistant then
  offers to uninstall it from the Marketplace.
- **The app:** Settings → Apps → ito → **Uninstall**. This deletes the node's identity
  unless you keep a backup.

## Early testers (before the first release)

**For development and early testing only** (maintainer decision A-4, 19 Nov 2026). Until images are
published, the app store can still install ito from this repository by **building it on your
device**: the same steps as above, but step 2 takes several minutes on a Raspberry Pi 4, needs
internet access for the build, and is more likely to fail. Use a test installation, not one you
depend on. To try an unreleased branch, add the repository as
`https://github.com/3LivesLeft/ito#<branch>`: the app store treats it as a **different app,
with its own data and identity**, so it never touches an installation from the main repository. The
older [local prototype guide](install-local-prototype.md) (copying the folder) still works.

## Privacy

Everything stays on your Home Assistant device. ito connects only to the peers you choose,
and the dashboard reads only your own Home Assistant. See the
[integration guide](home-assistant-integration.md#privacy-and-security).

## Help

- The app log explains each state in plain words. In the dashboard, **Diagnostics** shows
  versions, start times and restarts.
- [Troubleshooting in the app's documentation](../meshbeacon/DOCS.md).
- Already running the local prototype? Keep it for now: moving its identity to the published app
  is planned separately (it must not lose your node's identity), and you will be told how.
