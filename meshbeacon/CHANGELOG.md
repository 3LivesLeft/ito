# Changelog

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
