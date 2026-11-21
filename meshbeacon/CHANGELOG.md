# Changelog

## 0.5.0 — unreleased (develop)

- The dashboard is bundled in the app and opens through Home Assistant Ingress. App updates now update the dashboard, logo and fonts together.
- Adds the ito sidebar entry on first start. Choose connections and manage settings in the dashboard; Save and apply restarts ito and reconnects automatically.
- Messaging uses the existing engine and persistent store. Identities, contacts, messages, integration domain and app slug are unchanged.
- The Marketplace integration is optional, for entities and automations. Existing installations can keep it.
- Recent dashboard charts are held in memory (24 hours and 7 days); Home Assistant recorder history is untouched.


## 0.4.1 — unreleased (develop)

- **MeshBeacon is now called ito.** The app, the integration, the sidebar panel and its messages,
  the app's log and the documentation use the new name, with new provisional artwork (a thread
  around the earth) and a globe icon in the sidebar. Updating in place keeps everything: the app's
  data, your node and messaging identities and address, contacts, conversations, settings, and
  your existing entity IDs (`sensor.meshbeacon_…`). Only a new installation gets `sensor.ito_…`
  entity IDs. Optional: an "ito sage" theme for Home Assistant (`docs/home-assistant/ito-theme.yaml`).
- **The repository has moved to `https://github.com/3LivesLeft/ito`.** If you already have the app,
  change nothing: keep the repository address you added (with `#develop` if you used it). GitHub
  forwards the old address, so this update arrives as usual. Adding the new address instead
  installs a second, separate app with a new identity
  ([details](../docs/getting-started.md#the-repository-has-moved-installed-before-21-nov-2026)).

**To update:** Settings → Apps → MeshBeacon (ito once updated) → **Update** (not Rebuild), then update the integration if
Home Assistant offers it or a repair asks. Both should be 0.4.1.

## 0.4.0 — unreleased (develop)

- **Read and answer LXMF messages in Home Assistant.** The MeshBeacon dashboard has a new
  **Messages** tab: your contacts and conversations, unread counts, MeshBeacon's own address to
  copy, and a box to write and send replies. New messages and delivery changes appear without
  refreshing. Each message you send says honestly where it is: *Waiting to send*, *Sending…*,
  *Delivered* (only when the recipient's app confirmed it), *Stored on a propagation node*, or
  *Not delivered* with **Send again**.
- **Add, rename and remove contacts in the dashboard.** Paste a contact's LXMF address and give it
  a name. Contacts from the Configuration tab are kept and appear in the Messages tab.
- **Conversations are kept** by the app across restarts and updates (at most 10,000 messages; the
  oldest go first). They are never stored in Home Assistant's history, logs or diagnostics.
- **Automatic replies** are sent at most once every six hours per contact, so two automatic
  responders cannot answer each other for ever, and are marked as automatic in the conversation.
- Only Home Assistant administrators can read or send messages.
- **Fixed: the Messages tab no longer reconnects over and over.** Opening a conversation made the
  dashboard read it again and again, until it showed *Reconnecting* and *Too many messages in a
  short time*, the composer was disabled and the conversation looked empty. No messages, contacts
  or identities were affected. It now reads a conversation once and again only when something
  changes; if a read is refused or the app restarts, it waits a little longer each time and comes
  back by itself. Such refusals are now written to the app's and Home Assistant's logs.

**To update** (your node identity, messaging identity, contacts, conversations-to-be and settings
are all kept):

1. Settings → Apps → MeshBeacon (called **ito** after the update) → **Update** (not Rebuild), then
   **Start** if it is not running.
2. Settings → Devices & services: if Home Assistant offers an update for the **ito integration**
   (formerly MeshBeacon; or shows a repair asking for it), install it and restart Home Assistant
   when asked. The app and the integration must both be 0.4.0 for the Messages tab.
3. Open **ito** in the sidebar → **Messages**. If you have not yet, check that **Enable LXMF
   messaging** and **Show ito's status in Home Assistant** are both on in the app's Configuration
   tab.

## 0.3.1 — unreleased (develop)

- **Fixed: messaging still could not talk to Reticulum after the 0.3.0 messaging fix** on Home
  Assistant OS ("digest received was wrong", "Reticulum refused the engine's requests"). The fix
  needs a new rule in MeshBeacon's security (AppArmor) profile, and Home Assistant loads a new
  profile only when an app is installed or **updated**, not when it is rebuilt. This version
  number makes Home Assistant offer the update.
- **To update:** Settings → Apps → MeshBeacon → **Update** (not Rebuild), then start it. Your
  node and messaging identities, contacts and settings are kept. The log then shows
  "Reticulum accepts the engine's requests".
- If messaging ever lacks its key again, the dashboard and the log say so and what to do, instead
  of suggesting a restart that cannot help.

## 0.3.0 — unreleased (develop)

- **Choose a public network from a list** (Configuration tab, **Public Reticulum network**):
  Ratspeak Ruby, Emerald or Diamond, or ReticulumNet — no addresses to type. The default,
  `custom`, joins no public network, so MeshBeacon still connects to nobody until you choose.
  Your own peers keep working unchanged and are used alongside the chosen network. The log names
  the chosen network, and it appears with its connection status in the dashboard.
- **Optional LXMF messaging** (off by default). Tick **Enable LXMF messaging** in the
  Configuration tab and restart the app: MeshBeacon starts its own messaging service, with its own
  address, which LXMF apps such as Sideband can message. Add the people allowed to message it under
  **Messaging: contacts**. By default it answers each of their messages with a short confirmation,
  so you can check both directions; reading and sending messages from Home Assistant comes later.
  The dashboard shows whether messaging is off, starting, running or has a problem, and its
  address to copy. Switching it off stops only messaging; Reticulum keeps running and the
  messaging address is kept. One standard app for everyone: nothing of messaging runs while it is
  off.
- **Fixed: messaging could not talk to Reticulum** (seen on the first Raspberry Pi installation). Reticulum refused every request from the messaging service ("digest received was wrong" in the log, every ~10 s), while the dashboard still showed *Running*. The messaging service is now given Reticulum's access key, and nothing else of Reticulum's; the dashboard shows a problem if Reticulum ever refuses it. With messaging off nothing changes.
- Each part of MeshBeacon (the core, Reticulum, messaging) runs as its own user; credentials and
  data are visible only to the part that needs them.
- **Install from Home Assistant's own stores** (prepared; available from the first release): the
  app from the app store, the dashboard from Home Assistant's Marketplace (Home Assistant 2026.11
  or newer). No terminal and no copying of files.
- **Discovery over the Supervisor's local socket** where the Supervisor provides one: Home
  Assistant is told about MeshBeacon without anything crossing the internal network, and the
  Supervisor token is not used. Current Supervisors keep the previous method.
- The dashboard's integration keeps your entity IDs and history if the app is ever reinstalled
  from a different source, and it says which part to update when the app and the integration are
  out of step.
- No new permissions; the security rating is unchanged.

## 0.2.0 — unreleased (in development)

- **New option: "Show MeshBeacon's status in Home Assistant"** (off by default). When it is on,
  MeshBeacon offers its status to Home Assistant over the internal network only, protected by a
  key that changes at every start. Home Assistant then offers to add the MeshBeacon integration
  (included in this repository), which shows status, peers, traffic, known paths, relayed links,
  CPU, memory and restarts as sensors with history. It is read-only; nothing is sent anywhere else.
- The status is sent over HTTPS, with a certificate that changes at every start and that Home
  Assistant checks, so other apps on the internal network cannot read or alter it.
- No new permissions: the app uses Supervisor discovery, which needs no API access. The security
  rating is unchanged.
- If the Supervisor cannot be reached, MeshBeacon keeps trying by itself; no restart needed.
- The watchdog's health check is now protected against slow or flooding clients.
- Each problem now has a stable code alongside its plain-language message, for repair issues in
  Home Assistant.
- **MeshBeacon in the sidebar.** Once the integration is added, administrators get a MeshBeacon
  entry in Home Assistant's sidebar: connectivity at a glance, large figures, traffic, processor
  and memory history, a card for each peer, and a Diagnostics tab. It follows your theme (light or
  dark), works on phones, tablets and desktops, and uses only Home Assistant's own data and
  history. Nothing to configure, and no code loaded from the internet.
- **Fix:** the integration could occasionally reject a valid status reply that arrived in several
  pieces. It now reads the whole reply, still with a size limit.
- "Known paths" stopping at 2,048 is normal on a busy network: Reticulum trims paths it has never
  used. The panel explains this.
- The integration is ready for HACS, but is not offered through it yet.
- **New look.** MeshBeacon has its own logo, app icon and colours, used in the app store, on
  the app page, in the sidebar (lighthouse icon), in its panel and under Devices & services. The
  panel follows your light or dark theme, uses the Inter typeface bundled with it (nothing is
  loaded from the internet), and meets WCAG 2.2 AA contrast. Status is never shown by colour
  alone.

## 0.1.2 — unreleased (local prototype)

- The AppArmor profile now denies the `fsetid` capability explicitly. It was never granted; the
  change stops three harmless AppArmor denials from being logged on every start (the root init
  step's `chmod`), so that real denials stand out. Behaviour is unchanged.

## 0.1.1 — unreleased (local prototype)

- **Fix:** the app failed immediately on start on Home Assistant OS
  (`/bin/sh: can't open '/init': Permission denied`). The AppArmor profile allowed s6-overlay's
  start-up scripts to be executed but not read, which a shell script needs. The profile has been
  rewritten and is now tested under real AppArmor enforcement in CI.
- **Update with "Update", not "Rebuild":** Home Assistant loads an app's AppArmor profile only
  when the app is installed or updated to a new version. This version number change makes Home
  Assistant offer an update, which loads the corrected profile.
- Identity replacement is now crash-safe as a whole; slow start-up no longer risks a watchdog
  restart.

## 0.1.0 — unreleased (local prototype)

First local prototype of the v0.1.0 foundation. Not published; build and install it as a local
app (see DOCS.md). Experimental — do not depend on it yet.

- Runs the unmodified Reticulum reference implementation (RNS 1.6.0) as a supervised,
  non-root process.
- Manually configured outbound TCP peers; optional transport mode (off by default).
- Crash-safe, persistent node identity with verified backup and no silent replacement.
- Plain-language status messages, bounded recovery and resource guards.
