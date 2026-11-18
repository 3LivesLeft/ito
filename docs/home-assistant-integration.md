# Home Assistant integration (v0.2)

Status: **in development** on `feature/v0.2.0-observability`. Not published (no HACS release).
Design and security review: [v0.2 feasibility and architecture](research/v0.2-observability.md),
[ADR 0006](adr/0006-local-metrics-api.md).

## What it is

A read-only custom integration (`custom_components/meshbeacon`) that shows the MeshBeacon app's
status as Home Assistant entities. History and long-term statistics come from Home Assistant's own
recorder; MeshBeacon keeps none. Nothing leaves your Home Assistant installation.

## Set-up (local prototype)

1. Copy `custom_components/meshbeacon` into Home Assistant's `/config/custom_components/` and
   restart Home Assistant.
2. In the MeshBeacon app's Configuration tab, switch on **Show MeshBeacon's status in Home
   Assistant** and restart the app.
3. Settings → Devices & services shows **MeshBeacon discovered**. Choose **Add**.

There is no manual set-up: the app's key is never shown, typed or logged. It reaches Home
Assistant only through Supervisor discovery, and it changes at every app start; the integration
picks up the new key automatically. Switching the option off withdraws the discovery message; you
can then delete the integration.

> Do not install this on the reference Pi while the v0.1 stability test is running.

## Entities

All entities belong to one device, **MeshBeacon**. Diagnostic entities are under *Diagnostic*.

| Entity | Meaning |
|---|---|
| Status | `starting`, `running`, `restarting` or `needs_attention` |
| Connectivity | `isolated` (no peers), `offline` (none reachable), `partial`, `online`, `unknown` |
| Problem (binary) / Diagnosis | Whether something needs attention, and what (for example "Cannot reach any peer", "Identity problem") |
| Reticulum (binary), Transport mode (binary) | Whether Reticulum is running; whether the *running* Reticulum has transport on |
| App started, Reticulum started | Start times (uptime is "now minus start") |
| Peers connected / configured | Counts |
| Received, Sent | Bytes since Reticulum last started. They are `total_increasing`, so HA's statistics handle the reset after a restart |
| Receive rate, Send rate | Bytes per second averaged over the last minute |
| Packets received / sent (including own) | Every packet, the node's own included. Reticulum does not report forwarded packets separately |
| Known paths | Size of Reticulum's path table (routing table) |
| Relayed links | Links currently carried *through* this node in transport mode. This shows that forwarding is happening, not how much; it lags a peer going away until Reticulum expires the link |
| Announces received / sent | Totals over all peers |
| Memory, CPU | RSS + swap of all app processes; CPU as % of one core over the last minute |
| Reticulum restarts, Memory-limit restarts | Automatic restarts since the app started |
| *Peer* connected, *peer* connected since | Per peer, observed every 10 s (a drop shorter than 10 s may be missed) |
| *Peer* received / sent / rates / announces / reconnections | Per peer |

"Unknown" means Reticulum did not report the value (for example while it starts). It never
means zero.

## Repair issues

| Issue | When |
|---|---|
| MeshBeacon is not connected to anyone | No peers are configured |
| MeshBeacon cannot reach its peers | No peer reachable for 10 minutes |
| MeshBeacon needs your attention | MeshBeacon has stopped Reticulum until a cause is fixed; the app's message is shown |

## Dashboard

[`home-assistant/dashboard.yaml`](home-assistant/dashboard.yaml) is an example dashboard built
only from Home Assistant's own cards (tiles, history graphs, statistics graphs).

## Privacy and security

- Read-only. There is no endpoint that changes anything.
- The status contains no identity or destination hashes, peer hosts, network names, passphrases or
  keys. Peer names (which you chose) are included.
- Diagnostics downloads remove the key and host, and replace peer names.
- The status interface listens only on the app's internal network address (port 8100, not
  published) and exists only while the option is on.
