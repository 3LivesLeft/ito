# MeshBeacon

**Decentralised connectivity for your home.**

MeshBeacon runs a [Reticulum](https://github.com/markqvist/Reticulum) node on your Home Assistant
device. Reticulum is an encrypted, decentralised network that works over the internet today and,
in later versions of MeshBeacon, over radio as well.

> ⚠ **Experimental.** This is the v0.1.0 local prototype. Do not depend on it yet.

## What it does (v0.1.0)

- Runs the **unmodified Reticulum reference implementation** (RNS 1.6.0) for you.
- Connects to **peers you choose** — nothing else. With the default settings MeshBeacon makes
  **no external connections at all**.
- Keeps your node's **identity** (its address on the network) safe across restarts, updates and
  backups.
- Optionally **shares your connection** with others (transport mode, off by default).

From v0.2 it can also **show its status in Home Assistant** (optional, off by default; see
below). From v0.3 it can also run an **LXMF messaging service** (optional, off by default; see
below). It does not use radio.

## Installing and updating

From the first release, MeshBeacon installs from Home Assistant's own app store and updates under
**Settings → Updates**, with no terminal or file copying (Home Assistant 2026.11 or newer). Step
by step: `docs/getting-started.md` in the repository.

Until then, testers install it as a local app: `docs/install-local-prototype.md` in the
repository.

After the first successful start, switch on **Watchdog** on the app's Info tab (recommended).
MeshBeacon is designed so that the watchdog only restarts it if MeshBeacon itself stops
responding, never because your internet is down.

## Join a public network

The quickest way to get connected. No addresses to type.

1. Open the **Configuration** tab and choose one under **Public Reticulum network**:

   | Choice | Network | Run by | Address it connects to |
   |---|---|---|---|
   | `custom` (default) | none: only your own peers below | — | — |
   | `ratspeak_ruby` | Ruby | Ratspeak | `1.ratspeak.org`, port 4141 |
   | `ratspeak_emerald` | Emerald | Ratspeak | `2.ratspeak.org`, port 4242 |
   | `ratspeak_diamond` | Diamond | Ratspeak | `3.ratspeak.org`, port 4343 |
   | `reticulumnet` | ReticulumNet | Reticulum Netherlands | `node.reticulumnet.nl`, port 4242 |

   None of them needs a network name or passphrase. **Diamond** bans nodes that relay for 50
   remote peers or open more than 20 connections from one IP address, so do not combine it with
   transport mode (MeshBeacon warns you if you do).
2. **Save**, then **Restart** the app.
3. In the **Log** tab, look for *"Public network: Ratspeak Emerald"* and then *"Connected to
   Ratspeak Emerald. Your node is online."* The network also appears as a peer, with its
   connection status, in the MeshBeacon dashboard and in Home Assistant's entities.

Public networks are run by volunteers, with no uptime guarantee. If one is down, choose another.

## Connect to your own peers

A **peer** is another Reticulum node — for example a friend's node or your own node elsewhere.
Your own peers are used **together with** the public network you chose, if any. Leave the network
on `custom` to connect only to them.

1. Open the **Configuration** tab and add an entry under **Your own peers** (up to 10):
   - **name**: anything you like, e.g. `Home peer`
   - **host**: the peer's address, e.g. `rns.example.org` or an IP address
   - **port**: the peer's port, e.g. `4242`
   - **network name** and **passphrase**: only if the peer's operator gave you them
2. **Save**, then **Restart** the app.
3. In the **Log** tab, look for *"Connected to Home peer. Your node is online."*

MeshBeacon keeps reconnecting automatically if a peer or your internet connection drops. Peers you
added before the network selector existed keep working unchanged; if one of them is a network in
the list above, selecting it does not add it twice.

### Privacy when connecting to a public network or peer

- **The operator can see your home's public IP address**, when you are connected, and how
  much data passes through the connection.
- **They cannot read** your end-to-end-encrypted Reticulum traffic.
- They may keep logs; MeshBeacon cannot control what an operator records.
- They may go offline at any time, or ban connections that break their rules.
- MeshBeacon connects to **nobody** until you choose a network or add a peer.

## Transport mode

**Off** (recommended for most people): your node uses the network but does not carry other
people's traffic.

**On**: your node also passes traffic between other Reticulum users, which helps the network
grow. Only switch it on if Home Assistant is always on and your internet plan has data to spare.
Some public peers limit how many people may connect through you.

Note: with transport mode off, Reticulum uses a temporary network-facing identity that changes on
each start; with it on, your stored identity is used. MeshBeacon keeps the stored identity safe
either way.

## Your node's identity and backups

Your node's identity is a **private key** stored in the app's data folder. MeshBeacon:

- creates it safely on first start and checks it **before every start** of Reticulum;
- keeps a **verified backup copy** and restores from it automatically if the file is damaged;
- **never silently replaces it** — if both copies are damaged it stops and tells you;
- never writes it, or its address, to the log.

**Home Assistant backups include the private key.** Use encrypted backups, and do not share
backups with anyone. To move MeshBeacon to new hardware, restore the app from a Home Assistant
backup.

To deliberately start with a **new** identity: switch on **Advanced: replace identity on next
start**, restart the app, then switch it off again. The previous identity is kept in the app's data
folder. MeshBeacon will not start while the option is left on after a replacement.

## Messages you may see

| Message | What to do |
|---|---|
| ⚠ not connected to anyone | Choose a public network or add a peer (see above). Repeated every 6 hours as a reminder. |
| ⚠ cannot reach any of your peers | Check your internet connection and the peer details. MeshBeacon keeps trying. |
| ⚠ will try again in 15 minutes | Reticulum keeps failing; the lines above show why. |
| ✖ has stopped trying | Fix the cause shown above, then restart the app. |
| ✖ has paused to avoid a restart loop | The app was restarted many times quickly. Restart it after the time shown, or change any option. |
| ✖ identity … damaged … has NOT created a new one | Restore the app from a backup, or use *replace identity* if you want a new address. |
| ✖ some options need correcting | Fix the listed options in the Configuration tab. |
| ⚠ the link to the discovery relay was lost | Only with the Home Assistant option on, on newer Supervisors. Home Assistant keeps showing the status until the next app start; restart the app to restore the link. |
| Waiting for the discovery relay to start… | Normal on a busy or slow device at start-up; MeshBeacon waits up to 30 seconds and then starts anyway. |

MeshBeacon always stays "running" in Home Assistant while it waits for you, so that the watchdog
does not restart it pointlessly.

## Show MeshBeacon's status in Home Assistant (the dashboard)

This is optional and **off by default**.

1. Install the MeshBeacon integration once, from Home Assistant's Marketplace:
   [open MeshBeacon in the Marketplace](https://my.home-assistant.io/redirect/marketplace_repository/?owner=3LivesLeft&repository=meshbeacon&category=integration).
   Until MeshBeacon is in the Marketplace's catalog, Home Assistant asks you to connect GitHub
   first (read-only). If Home Assistant asks for a restart, use the repair it shows.
2. Switch on **Show MeshBeacon's status in Home Assistant** in the Configuration tab and restart
   the app.
3. Home Assistant shows **MeshBeacon discovered** under Settings → Devices & services. Choose
   **Add**.

You get sensors for status, connectivity, peers, traffic, known paths, links relayed for others,
processor and memory use and restarts. Home Assistant keeps their history and statistics itself. An
example dashboard is in the repository (`docs/home-assistant/dashboard.yaml`).

- **Status is read-only.** Home Assistant cannot control your node. With messaging on,
  administrators can read and send messages and edit contacts in the Messages tab; nothing else.
- **Private.** The status stays on Home Assistant's internal network, encrypted, and protected by
  a key and a certificate that change every time the app starts. It contains no addresses, keys,
  passphrases or network names. Nothing is sent anywhere else.
- **How Home Assistant gets the key.** MeshBeacon hands the key to Home Assistant through the
  Supervisor. Newer Supervisors provide a local socket for this, and MeshBeacon uses it
  automatically. On current Supervisors the hand-over crosses the internal network without
  encryption, so another installed app able to spoof on that network might read the key; this has
  not been demonstrated. The status key only allows reading the status, until the next app start.
  With messaging on, a separate messaging key travels the same way and would allow reading and
  sending messages until the next app start (an accepted risk; Home Assistant keeps that key in
  memory only). You can
  reduce this risk with the Supervisor's advanced `app_drop_net_raw` feature flag.
- **Honest numbers.** Anything Reticulum does not report is shown as "unknown". **Links relayed for
  others** shows that transport mode is carrying other people's connections. It is not a count of
  forwarded packets, which Reticulum does not report, so MeshBeacon does not show one.
- After an app restart, the sensors are unavailable briefly while Home Assistant receives the new
  key. This happens by itself.
- Home Assistant keeps the current key in its configuration (and so in its backups). It only allows
  reading the status, and stops working at the next app start.

Full details: `docs/home-assistant-integration.md` in the repository.

## LXMF messaging (optional, experimental)

MeshBeacon can run an LXMF messaging service, so that apps such as Sideband can send it messages.
It is **off** unless you switch it on.

1. Open the **Configuration** tab and tick **Enable LXMF messaging**.
2. Make sure **Show MeshBeacon's status in Home Assistant** is on too (the Messages tab needs it).
3. **Save**, then **Restart** the app. The log says `LXMF messaging: on`.
4. Open **MeshBeacon** in Home Assistant's sidebar → **Messages**. Copy MeshBeacon's address and add
   it as a contact in your app.
5. Choose **Add contact** and paste your app's own LXMF address (32 characters, shown in your app).
6. Send MeshBeacon a message from your app. It appears in the Messages tab; type a reply and press
   **Send**. Below each message you send, MeshBeacon says whether it is waiting, sending, delivered
   (only when your app confirmed it) or stored on a propagation node.

Contacts can also be listed under **Messaging: contacts**; they are added to the Messages tab when
the app starts, and you manage them there afterwards. **Messaging: automatic reply** answers a
contact at most once every six hours.

Both sides must be on the same Reticulum network, for example connected to the same peer.

- **Its own address.** Messaging has its own identity, separate from your node's, created the first
  time and kept in the app's data and backups. Switching messaging off stops only messaging;
  Reticulum keeps running, and the address is kept for next time.
- **Strangers.** Only your contacts can message MeshBeacon unless you switch on **Messaging: accept
  messages from anyone**; then each sender's app must do a small proof-of-work calculation
  ("stamp") per message, which keeps spam away.
- **Message text.** Conversations are kept by the app (up to 10,000 messages) so that they survive
  restarts and updates; only Home Assistant administrators can read them, in the Messages tab.
  They never appear in the app log or in Home Assistant's history, logbook or diagnostics. Delete a
  conversation or remove a contact from the ⋮ menu. While messaging is off they are kept, not shown.
- **Privacy.** With a display name left empty (the default), MeshBeacon's announcement carries no
  name. The messaging address is shown on the dashboard but not stored in Home Assistant's history.
- **If something is wrong**, the Messaging card says what, in plain words (for example a contact
  address that is not 32 characters, or a damaged messaging identity, which MeshBeacon never
  replaces: restore the app from a backup). Reticulum is never stopped because of messaging.

## Resource use

MeshBeacon is designed to be light: about 65–70 MB of memory when idle (measured in containers on
x86-64; Raspberry Pi measurement pending). With messaging on, about 45 MB more. It runs Reticulum at low priority, restarts it if it uses
more memory than the limit you set (default 256 MB), limits how much it writes to the log, and stops
Reticulum if free storage falls below 200 MB.

## Security and privacy

- No host networking, no published ports, no access to the Home Assistant or Supervisor APIs, no
  extra privileges or devices. Runs as a dedicated non-root user.
- No telemetry, analytics or "phone home".
- Apps with elevated privileges (for example an SSH app with protection mode disabled) can read
  other apps' data, including MeshBeacon's identity. Keep protection mode enabled.

Report security problems privately — see `SECURITY.md` in the repository.

## Licences

MeshBeacon is licensed under Apache-2.0. It includes Reticulum (RNS) and LXMF, licensed under the
**Reticulum License**, which is not an OSI-approved open-source licence: it forbids use in systems
designed to harm human beings and use in creating AI or machine-learning training datasets. Those
conditions apply to you as a user of this app. Full notices: `THIRD_PARTY_NOTICES`.
