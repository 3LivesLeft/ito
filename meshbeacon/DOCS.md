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

It does not yet show entities or dashboards in Home Assistant, send messages, or use radio.

## Install as a local app (prototype)

MeshBeacon is not published yet, so you install it from a copy of its folder:

1. Install the **Samba share** or **Advanced SSH & Web Terminal** app if you have neither.
2. Copy the `meshbeacon` folder from this repository into the `addons` folder on your Home
   Assistant device (it appears as `/addons` over SSH, or the **addons** share over Samba), so
   that you have `/addons/meshbeacon/config.yaml`.
3. Go to **Settings → Apps → App store**, open the ⋮ menu and choose **Check for updates**.
4. **MeshBeacon** appears under **Local apps**. Open it and select **Install**. Home Assistant
   builds it on your device; on a Raspberry Pi 4 this takes a few minutes and needs an internet
   connection to download the base image and the pinned Python packages.
5. Start it, then open the **Log** tab. You will see:
   *"MeshBeacon is running, but it is not connected to anyone."* — that is expected until you add
   a peer.
6. Optional but recommended: switch on **Watchdog** on the app's Info tab. MeshBeacon is designed
   so that the watchdog only restarts it if MeshBeacon itself stops responding — never because
   your internet is down.

## Connect to a peer

A **peer** is another Reticulum node — for example a friend's node, your own node elsewhere, or a
public entry point you have chosen to trust.

1. Open the **Configuration** tab and add an entry under **Your own peers**:
   - **name**: anything you like, e.g. `Home peer`
   - **host**: the peer's address, e.g. `rns.example.org` or an IP address
   - **port**: the peer's port, e.g. `4242`
   - **network name** and **passphrase**: only if the peer's operator gave you them
2. **Save**, then **Restart** the app.
3. In the **Log** tab, look for *"Connected to Home peer. Your node is online."*

MeshBeacon keeps reconnecting automatically if the peer or your internet connection drops.

### Privacy when connecting to a peer

- **The peer's operator can see your home's public IP address**, when you are connected, and how
  much data passes through the connection.
- **They cannot read** your end-to-end-encrypted Reticulum traffic.
- They may keep logs; MeshBeacon cannot control what an operator records.
- They may go offline at any time, or ban connections that break their rules.
- MeshBeacon v0.1.0 ships **no preset public peers**: you decide whom to connect to.

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
| ⚠ not connected to anyone | Add a peer (see above). Repeated every 6 hours as a reminder. |
| ⚠ cannot reach any of your peers | Check your internet connection and the peer details. MeshBeacon keeps trying. |
| ⚠ will try again in 15 minutes | Reticulum keeps failing; the lines above show why. |
| ✖ has stopped trying | Fix the cause shown above, then restart the app. |
| ✖ has paused to avoid a restart loop | The app was restarted many times quickly. Restart it after the time shown, or change any option. |
| ✖ identity … damaged … has NOT created a new one | Restore the app from a backup, or use *replace identity* if you want a new address. |
| ✖ some options need correcting | Fix the listed options in the Configuration tab. |

MeshBeacon always stays "running" in Home Assistant while it waits for you, so that the watchdog
does not restart it pointlessly.

## Resource use

MeshBeacon is designed to be light: about 70 MB of memory when idle (measured in a container on
x86-64; Raspberry Pi measurement pending). It runs Reticulum at low priority, restarts it if it uses
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

MeshBeacon is licensed under Apache-2.0. It includes Reticulum (RNS), licensed under the
**Reticulum License**, which is not an OSI-approved open-source licence: it forbids use in systems
designed to harm human beings and use in creating AI or machine-learning training datasets. Those
conditions apply to you as a user of this app. Full notices: `THIRD_PARTY_NOTICES`.
