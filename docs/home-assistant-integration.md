# Home Assistant integration (v0.2)

Status: **in development** on `feature/v0.2.0-observability` (draft PR #3). Not published (no
HACS release). Design and security review: [v0.2 feasibility, architecture and security](research/v0.2-observability.md),
[ADR 0006](adr/0006-local-metrics-api.md). Hardware test: [v0.2 hardware acceptance](testing/v0.2-hardware-acceptance.md).

## What it is

A **read-only** custom integration (`custom_components/meshbeacon`) that shows the MeshBeacon app's
status as Home Assistant entities. History and long-term statistics come from Home Assistant's own
recorder; MeshBeacon keeps none. Nothing leaves your Home Assistant installation, and Home
Assistant cannot control the node through it.

## Set-up

1. **Install the integration once.** Copy `custom_components/meshbeacon` into Home Assistant's
   `/config/custom_components/` (for example with the File editor or Samba app), then restart
   Home Assistant.
2. **Switch it on in the app.** In the MeshBeacon app's Configuration tab, switch on **Show
   MeshBeacon's status in Home Assistant** (off by default), save, and restart the app.
3. **Add it.** Settings → Devices & services shows **MeshBeacon discovered**. The dialog names the
   app it came from (`local_meshbeacon` for a local install). Choose **Add**.

Nothing else needs configuring:
- There is no key to copy or type. The key and the certificate fingerprint reach Home Assistant
  only through Supervisor discovery, and both change at every app start; the integration picks up
  the new ones by itself.
- The order of steps 1 and 2 does not matter: Home Assistant looks at waiting discovery messages
  whenever it starts.
- If "MeshBeacon discovered" does not appear, check the app log. It says whether Home Assistant has
  been told. If it has, the integration is probably not installed: repeat step 1.

**To remove it:** switch the option off and restart the app, then delete the integration under
Devices & services, and optionally its folder.

> Do not install this on the reference Pi while the v0.1 stability test is running.

## Entities

All entities belong to one device, **MeshBeacon**. Status is read every **60 seconds**.
Entities marked "off" are disabled by default because they change at every update and would add
recorder rows; enable them on the entity's settings page if you need them.

| Entity | Meaning | Default |
|---|---|---|
| Status | Starting, Running, Restarting or Needs attention | On |
| Connectivity | Isolated (no peers), Offline (none reachable), Partly connected, Online, Unknown | On |
| Problem | On when something needs attention | On |
| Problem details | What it is, for example "Cannot reach any peer" or "Identity problem" | On |
| Reticulum running | Whether the Reticulum service is running | On |
| Transport mode | Whether the *running* Reticulum has transport mode on | On |
| App started, Reticulum started | Start times (uptime is now minus start) | On |
| Peers connected, Peers configured | Counts | On |
| Data received, Data sent | Bytes since Reticulum last started (HA's statistics handle the reset after a restart) | On |
| Receive rate, Send rate | Bytes per second, averaged over the last minute | On |
| Known paths | Size of Reticulum's path table (its routing table) | On |
| **Links relayed for others** | Links that other people's traffic is using *through* your node in transport mode | On |
| Memory use | RSS + swap of all the app's processes, in whole MiB | On |
| Processor use | Percentage of one CPU core over the last minute | On |
| Reticulum restarts, Memory-limit restarts | Automatic restarts since the app started | On |
| Packets received / sent (all traffic) | Every packet, your node's own included | Off |
| Announces received / sent | Announces exchanged with all peers | Off |
| Memory use (MeshBeacon core / Reticulum) | Memory per process | Off |
| *Peer* connected, *peer* connected since | Per peer, checked every 10 s by the app (a drop shorter than 10 s may be missed) | On |
| *Peer* reconnections | Times the peer reconnected since the app started | On |
| *Peer* data received / sent, receive / send rate, announces | Per-peer traffic detail | Off |

**Links relayed, not packets forwarded.** Reticulum reports how many links pass *through* your
node, not how many packets it forwarded for others, so MeshBeacon shows the former and does not
guess the latter. A value above zero means your node is helping the network. The count lags a
peer going away until Reticulum expires the link.

"Unknown" means Reticulum did not report the value (for example while it starts). It never
means zero.

## Repair issues

| Issue | When |
|---|---|
| MeshBeacon is not connected to anyone | No peers are configured |
| MeshBeacon cannot reach its peers | No peer reachable for 10 minutes |
| MeshBeacon needs your attention | MeshBeacon has stopped Reticulum until a cause is fixed; the app's message is shown |

## Dashboard

[`home-assistant/dashboard.yaml`](home-assistant/dashboard.yaml) is an example dashboard built only
from Home Assistant's own cards (tiles, history graphs, statistics graphs), using only entities
that are on by default.

## Storage used in Home Assistant

About **2 MB a day** of recorder history at most, and about **19 MB** over Home Assistant's default
10 days. This is a worst case measured with every value changing at every update; it barely grows
with more peers. Enabling the "off" entities adds more. Use the recorder's `exclude` option to drop
any entity.

## Privacy and security

- **Read-only.** There is no endpoint that changes anything.
- **Private.** The status stays on Home Assistant's internal network, over HTTPS with a certificate
  that changes at every app start. Home Assistant checks it against the fingerprint it received
  through the Supervisor, so other apps cannot read or alter it. No port is published, and nothing
  listens while the option is off.
- **No identifiers.** The status contains no identity or destination hashes, peer hosts, network
  names, passphrases or keys. Peer names, which you chose, are included.
- **Spoofing.** Discovery is accepted only from a MeshBeacon app, pointing at that app itself.
- **Diagnostics downloads** remove the key and host and replace peer names.
- **Where the key is kept.** Home Assistant stores the current key in its configuration, so it is
  in Home Assistant backups. It only allows reading this status, and it stops working at the next
  app start. MeshBeacon itself never stores it.
