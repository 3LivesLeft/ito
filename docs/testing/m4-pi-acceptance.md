# Testing M4 on the reference Raspberry Pi

**Status: ready to run; not run yet.** Nothing has been installed on the Pi by the development
session. This replaces the earlier procedure with separate test apps: since D-M4-8 there is one
standard MeshBeacon app, and this is the normal installation. Record results in
[M4 results](m4-results.md) with no household identifiers (no addresses, hostnames, URLs or
identity hashes; write `<address>` instead).

**What it covers:** MS-18 (memory and CPU with messaging on), the Pi half of MS-1 (messaging off),
and MS-14 with Sideband (and Ratspeak if you have it). **Time:** about 2 hours, most of it waiting.
**You need:** the Samba share app (or the File editor app), and a phone with Sideband.

## 1. Before you start

1. **Settings → System → Backups → Backup now** (a full backup). It holds your current MeshBeacon,
   its node identity and options. Wait until it is listed.
2. On the MeshBeacon app's **Configuration** tab, write down your peers (name, host, port, network
   name and passphrase) and whether transport mode is on. A fresh install starts without them.
3. Note the dashboard's **Memory use** and **Processor use** now (v0.2, for MS-1).

## 2. Remove the current MeshBeacon app

1. **Settings → Apps → MeshBeacon → Stop**, then **Uninstall**. This deletes the app's data,
   including the node identity; the backup from step 1 keeps it (see *Roll back*). Leave the
   MeshBeacon integration and the `addons/meshbeacon` folder as they are.

> **To keep your node's current address instead:** skip steps 2–3, replace the `addons/meshbeacon`
> folder (Samba share) with the `meshbeacon` folder from the ZIP in step 4, then **App store → ⋮ →
> Check for updates → MeshBeacon → Update** (not Rebuild). Your identity, peers and options are kept
> and messaging stays off. Then continue at step 4.

## 3. Install MeshBeacon from its repository

1. **Settings → Apps → App store → ⋮ → Repositories**, add
   `https://github.com/3LivesLeft/meshbeacon#develop` (the `#develop` part makes Home Assistant
   follow the `develop` branch) and close the dialog.
2. Find **MeshBeacon** (version 0.3.0) in the store and **Install**. Home Assistant builds it on
   the Pi; this takes several minutes.
3. On its **Configuration** tab, enter your peers and transport mode as before, switch on **Show
   MeshBeacon's status in Home Assistant**, and leave **Enable LXMF messaging** off. Save.
4. On the **Info** tab, leave **Watchdog** off for now and select **Start**.

| Check | Pass |
|---|---|
| Log | `MeshBeacon 0.3.0 starting`, `LXMF messaging: off`, then "Connected to …" within 2 minutes |
| Security rating (Info tab) | 8, as before |
| Home Assistant | "MeshBeacon discovered" is offered or the existing entry reconnects; add it if asked |

## 4. Update the dashboard (the integration)

The dashboard's messaging card is in the updated integration. Until there is a release, it is
copied by hand (no terminal):

1. On a computer, download `https://github.com/3LivesLeft/meshbeacon/archive/refs/heads/develop.zip`
   and unzip it.
2. With the Samba share, open `config/custom_components/`, rename `meshbeacon` to `meshbeacon.bak`
   and move it **out** of `custom_components`, then copy in the ZIP's `custom_components/meshbeacon`.
3. **Settings → System → Restart** Home Assistant.

| Check | Pass |
|---|---|
| MeshBeacon dashboard (sidebar) | Your node as before, plus a **Messaging** card saying **Off** |
| After 1 hour | **Memory use** and **Processor use**: messaging off (MS-1: memory within ±2 MiB of step 1.3 when measured the same way) |

## 5. Switch messaging on

1. On Sideband, find its own LXMF address (it is shown with your identity in the app).
2. In MeshBeacon's **Configuration** tab: tick **Enable LXMF messaging**; under **Messaging:
   contacts** add a name (for example `My phone`) and Sideband's address. Save, then **Restart**
   the app.

| Check | Pass |
|---|---|
| Log | `LXMF messaging: on`, then `meshbeacon-messaging: started (identity created)`; Reticulum still connected; no restarts |
| Dashboard | **Messaging: Running**, with MeshBeacon's messaging address and a **Copy** button |
| Restart the app once more | `meshbeacon-messaging: started (identity unchanged)`, the same address |

## 6. Message with Sideband (MS-14)

Sideband must reach the same Reticulum network as MeshBeacon, for example by connecting to the same
peer (a TCP connection to the host and port in your MeshBeacon peers).

| # | Do | Pass |
|---|---|---|
| 1 | In Sideband, add a conversation with MeshBeacon's address (paste it from **Copy**) | Accepted |
| 2 | Send "hello" | Sideband shows it **delivered**; the dashboard's *Messages received* goes up; *Last message* says "from My phone" |
| 3 | Wait | Sideband receives "MeshBeacon received your message…"; the dashboard's *Last confirmation* shows **Delivered** |
| 4 | Restart the MeshBeacon app, then send again | Steps 2–3 work again; same MeshBeacon address |
| 5 | Remove your phone from the contacts, save, restart; send again | Not accepted: *Messages received* unchanged, *Messages refused* goes up, no confirmation |
| 6 | Tick **Messaging: accept messages from anyone**, save, restart; send from Sideband (not a contact) | Accepted, because Sideband adds a proof-of-work stamp (MeshBeacon announces cost 8). No confirmation is sent to strangers |
| 7 | Optional: Ratspeak, steps 1–3 | As Sideband |
| 8 | Optional, if you run a propagation node: set **Messaging: propagation node**, turn Sideband off, let MeshBeacon reply, turn Sideband on | The confirmation shows **Stored on propagation node**, then reaches Sideband |

Afterwards put your phone back as a contact and switch "accept messages from anyone" off again.

## 7. Watch it for an hour (MS-18)

With messaging on and the app left alone for 1 hour:

| Reading | Where | Pass |
|---|---|---|
| Memory use | Dashboard | **At most 40 MiB more** than the messaging-off reading in step 4 (containers measured +44 MiB: this is the deciding measurement, D-M4-7), and **at most 160 MiB** in total |
| Memory use (messaging) | Dashboard → Diagnostics (enable the entity first) | The engine's own share |
| Processor use | Dashboard | At most 0.5 percentage points more than with messaging off |
| Connectivity, peers | Dashboard | As before; no Reticulum restarts |
| Log | App's Log tab | No ⚠ about messaging; no tracebacks |

## 8. Switch it off again

Untick **Enable LXMF messaging**, save, restart. **Pass:** log `LXMF messaging: off`; the card says
**Off**; Reticulum stays connected. Switch it back on and restart: the same messaging address.

## Roll back

1. **Settings → Apps → MeshBeacon → Uninstall** (the repository version).
2. **Settings → System → Backups**, open the backup from step 1 and restore only the
   **MeshBeacon** app (partial restore). This brings back v0.2.0 with your node identity and options.
3. To return the dashboard to v0.2: delete `config/custom_components/meshbeacon`, move
   `meshbeacon.bak` back in its place as `meshbeacon`, and restart Home Assistant.
4. Optionally remove the repository (**App store → ⋮ → Repositories**).

If anything else looks wrong, restore the whole backup.
