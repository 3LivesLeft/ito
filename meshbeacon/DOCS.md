# ito

**Decentralised connectivity for your home.**

ito runs a [Reticulum](https://github.com/markqvist/Reticulum) node on your Home Assistant
device. Reticulum is an encrypted, decentralised network that works over the internet today and,
in later versions of ito, over radio as well.

> ⚠ **Experimental.** This project is under active development. Do not rely on it for critical communications. Feature availability depends on the installed build.

## Core capabilities

- Runs the **unmodified Reticulum reference implementation** (RNS 1.6.0) for you.
- Connects to **peers you choose** — nothing else. With the default settings ito makes
  **no external connections at all**.
- Keeps your node's **identity** (its address on the network) safe across restarts, updates and
  backups.
- Optionally **shares your connection** with others (transport mode, off by default).

The optional Home Assistant integration exposes read-only status entities (see below). Messaging support is being developed separately; check the current release notes and dashboard before relying on two-way LXMF messaging. LoRa radio support requires compatible hardware and is not part of the basic local installation.

## Install as a local app (prototype)

ito is not published yet, so you install it from a copy of its folder:

1. Install the **Samba share** or **Advanced SSH & Web Terminal** app if you have neither.
2. Copy the `meshbeacon` folder from this repository into the local apps folder on your Home
   Assistant device. Depending on the Samba or SSH app's version it appears as `/local_apps` or
   `/addons` (the same folder), so that you have `…/meshbeacon/config.yaml`. Step-by-step
   instructions: `docs/install-local-prototype.md` in the repository.
3. Go to **Settings → Apps → App store**, open the ⋮ menu and choose **Check for updates**.
4. **ito** appears under **Local apps**. Open it and select **Install**. Home Assistant
   builds it on your device; on a Raspberry Pi 4 this takes a few minutes and needs an internet
   connection to download the base image and the pinned Python packages.
5. Start it, then open the **Log** tab. You will see:
   *"ito is running, but it is not connected to anyone."* — that is expected until you add
   a peer.
6. After this first successful start, switch on **Watchdog** on the app's Info tab (recommended).
   ito is designed so that the watchdog only restarts it if ito itself stops
   responding — never because your internet is down. Leave it off until the first start has
   succeeded: if the app cannot start at all, the watchdog only restarts it in quick succession.

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

ito keeps reconnecting automatically if the peer or your internet connection drops.

### Privacy when connecting to a peer

- **The peer's operator can see your home's public IP address**, when you are connected, and how
  much data passes through the connection.
- **They cannot read** your end-to-end-encrypted Reticulum traffic.
- They may keep logs; ito cannot control what an operator records.
- They may go offline at any time, or ban connections that break their rules.
- The local prototype ships **no preset public peers**: you decide whom to connect to.

## Transport mode

**Off** (recommended for most people): your node uses the network but does not carry other
people's traffic.

**On**: your node also passes traffic between other Reticulum users, which helps the network
grow. Only switch it on if Home Assistant is always on and your internet plan has data to spare.
Some public peers limit how many people may connect through you.

Note: with transport mode off, Reticulum uses a temporary network-facing identity that changes on
each start; with it on, your stored identity is used. ito keeps the stored identity safe
either way.

## Your node's identity and backups

Your node's identity is a **private key** stored in the app's data folder. ito:

- creates it safely on first start and checks it **before every start** of Reticulum;
- keeps a **verified backup copy** and restores from it automatically if the file is damaged;
- **never silently replaces it** — if both copies are damaged it stops and tells you;
- never writes it, or its address, to the log.

**Home Assistant backups include the private key.** Use encrypted backups, and do not share
backups with anyone. To move ito to new hardware, restore the app from a Home Assistant
backup.

To deliberately start with a **new** identity: switch on **Advanced: replace identity on next
start**, restart the app, then switch it off again. The previous identity is kept in the app's data
folder. ito will not start while the option is left on after a replacement.

## Messages you may see

| Message | What to do |
|---|---|
| ⚠ not connected to anyone | Add a peer (see above). Repeated every 6 hours as a reminder. |
| ⚠ cannot reach any of your peers | Check your internet connection and the peer details. ito keeps trying. |
| ⚠ will try again in 15 minutes | Reticulum keeps failing; the lines above show why. |
| ✖ has stopped trying | Fix the cause shown above, then restart the app. |
| ✖ has paused to avoid a restart loop | The app was restarted many times quickly. Restart it after the time shown, or change any option. |
| ✖ identity … damaged … has NOT created a new one | Restore the app from a backup, or use *replace identity* if you want a new address. |
| ✖ some options need correcting | Fix the listed options in the Configuration tab. |

ito always stays "running" in Home Assistant while it waits for you, so that the watchdog
does not restart it pointlessly.

## Show ito's status in Home Assistant (v0.2)

This is optional and **off by default**.

1. Install the ito integration once: copy `custom_components/meshbeacon` from the
   repository into `/config/custom_components/` and restart Home Assistant.
2. Switch on **Show ito's status in Home Assistant** in the Configuration tab and restart
   the app.
3. Home Assistant shows **ito discovered** under Settings → Devices & services. Choose
   **Add**.

You get sensors for status, connectivity, peers, traffic, known paths, links relayed for others,
processor and memory use and restarts. Home Assistant keeps their history and statistics itself. An
example dashboard is in the repository (`docs/home-assistant/dashboard.yaml`).

- **Read-only.** Home Assistant can see the status but cannot control your node.
- **Private.** The status stays on Home Assistant's internal network, encrypted, and protected by
  a key and a certificate that change every time the app starts. Other apps cannot read it. It
  contains no addresses, keys, passphrases or network names. Nothing is sent anywhere else.
- **Honest numbers.** Anything Reticulum does not report is shown as "unknown". **Links relayed for
  others** shows that transport mode is carrying other people's connections. It is not a count of
  forwarded packets, which Reticulum does not report, so ito does not show one.
- After an app restart, the sensors are unavailable briefly while Home Assistant receives the new
  key. This happens by itself.
- Home Assistant keeps the current key in its configuration (and so in its backups). It only allows
  reading the status, and stops working at the next app start.

Full details: `docs/home-assistant-integration.md` in the repository.

## Resource use

ito is designed to be light: about 65–70 MB of memory when idle (measured in containers on
x86-64; Raspberry Pi measurement pending). It runs Reticulum at low priority, restarts it if it uses
more memory than the limit you set (default 256 MB), limits how much it writes to the log, and stops
Reticulum if free storage falls below 200 MB.

## Security and privacy

- No host networking, no published ports, no access to the Home Assistant or Supervisor APIs, no
  extra privileges or devices. Runs as a dedicated non-root user.
- No telemetry, analytics or "phone home".
- Apps with elevated privileges (for example an SSH app with protection mode disabled) can read
  other apps' data, including ito's identity. Keep protection mode enabled.

Report security problems privately — see `SECURITY.md` in the repository.

## Licences

ito is licensed under Apache-2.0. It includes Reticulum (RNS), licensed under the
**Reticulum License**, which is not an OSI-approved open-source licence: it forbids use in systems
designed to harm human beings and use in creating AI or machine-learning training datasets. Those
conditions apply to you as a user of this app. Full notices: `THIRD_PARTY_NOTICES`.
