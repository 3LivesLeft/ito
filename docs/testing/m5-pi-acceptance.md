# M5 acceptance on the reference Pi (Ratspeak)

Final acceptance for two-way messaging in Home Assistant ([ADR 0024](../adr/0024-messaging-in-home-assistant.md)).
Record results without household identifiers (no addresses, hostnames or IPs; CLAUDE.md rule 15).

## Before

1. Take a Home Assistant backup that includes the MeshBeacon app.
2. Update **the installed** MeshBeacon app to 0.4.0 (Settings → Apps → MeshBeacon → **Update**, not
   Rebuild; do not add the repository again with another branch, which would create a separate app
   with a new identity). Start it.
3. Update the MeshBeacon integration to 0.4.0 the way it was installed, and restart Home Assistant
   if asked. No "update the integration" repair remains.
4. In the app's Configuration tab: **Enable LXMF messaging** and **Show MeshBeacon's status in Home
   Assistant** both on.

## Steps

| ID | Step | Expected |
|---|---|---|
| M5-1 | App log after start | Same node identity (`unchanged`), messaging identity `unchanged`, "Reticulum accepts the engine's requests" |
| M5-2 | Sidebar → MeshBeacon → **Messages** | "Messaging is working"; MeshBeacon's address equals the one shown before the update; contacts from the Configuration tab are listed |
| M5-3 | If Ratspeak is not yet a contact: **Add contact**, paste Ratspeak's address | The contact appears; no restart needed |
| M5-4 | Send a message from Ratspeak | It appears in the conversation within seconds, **without refreshing**; unread count shown until opened |
| M5-5 | Type a reply, press **Send** (try a double click) | One message; state goes Waiting/Sending → **Delivered**; it arrives once in Ratspeak |
| M5-6 | Reply again from Ratspeak | Appears in Home Assistant without refreshing |
| M5-7 | Restart the MeshBeacon app; reopen Messages | The whole conversation is still there, in order |
| M5-8 | Stop Ratspeak (or go offline), send from Home Assistant | Not shown as Delivered; "Not reached yet, trying again" (or "Stored on a propagation node" if one is configured); delivered after Ratspeak returns |
| M5-9 | Switch messaging off, restart | Messages tab says messaging is off and that conversations are kept; the node keeps running |
| M5-10 | Switch it on again, restart | Conversation and contacts back; same address |
| M5-11 | Log in as a non-administrator | No MeshBeacon panel; messages not reachable |
| M5-12 | Download the integration's diagnostics; search HA's history/logbook | No message text, no messaging key, no contact address |

## Rolling back

Restore the backup taken before updating (app and integration together).
