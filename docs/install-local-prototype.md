# Installing the MeshBeacon local prototype on Home Assistant OS

Status: v0.1.0 **local prototype** — experimental. No container image is published: Home Assistant
builds the app on your own device from this repository's `meshbeacon/` folder.

These instructions are written for the reference device (Raspberry Pi 4B, Home Assistant OS 18.5,
`aarch64`) but apply to any Home Assistant OS installation on `aarch64` or `amd64`.

> **Before you start**
> - Take a **full Home Assistant backup** (*Settings → System → Backups → Backup now*).
> - The build needs an internet connection: Home Assistant downloads the digest-pinned base image
>   from `ghcr.io`, Alpine security updates, and the hash-pinned Python packages from PyPI.
> - MeshBeacon makes **no Reticulum connections** until you add a peer.
> - Never post logs, backups or screenshots that show IP addresses, hostnames or your
>   configuration's passphrases.

## 1. Get the app folder

On a computer, download the repository at the branch or commit you want to test, for example from
GitHub: *Code → Download ZIP* on the `feature/v0.1.0-foundation` branch (or `main` once merged).
Unzip it. You need only the **`meshbeacon`** folder inside it (the one that contains
`config.yaml`, `Dockerfile` and `DOCS.md`).

## 2. Copy it to your Home Assistant

Home Assistant keeps local apps in one folder. Depending on the version of the Samba or SSH app,
that folder appears as **`/local_apps`** (current naming) or **`/addons`** (older naming) — they are
the same folder [Verified: Supervisor 2026.11.0, `supervisor/docker/app.py` maps it to either path].
Below, `<local apps folder>` means whichever of the two your app shows.

Use **one** of the following (both are official Home Assistant apps).

**Option A — Samba share**

1. *Settings → Apps → App store*, install **Samba share**, set a username and password in its
   Configuration tab, and start it.
2. On your computer, open the share for the local apps folder — named `local_apps` or `addons`
   depending on the Samba app's version — at `\\<homeassistant-host>\<share>` (Windows) or
   `smb://<homeassistant-host>/<share>` (macOS/Linux).
3. Copy the `meshbeacon` folder into it, so that the share contains `meshbeacon/config.yaml`.

**Option B — Advanced SSH & Web Terminal** (you already have it)

1. In the SSH terminal, run `ls -d /local_apps /addons 2>/dev/null` to see which name your SSH
   app uses.
2. Copy the folder to the device, for example with
   `scp -r meshbeacon root@<homeassistant-host>:<local apps folder>/` (the SSH app must be
   configured to accept your key or password).
3. Check: `ls <local apps folder>/meshbeacon/config.yaml` shows the file.

> Keep the SSH app's **protection mode enabled**. With it disabled, the SSH app can read other
> apps' data, including MeshBeacon's private key.

## 3. Install MeshBeacon

1. *Settings → Apps → App store*, open the **⋮** menu (top right) and choose **Check for updates**.
2. Scroll to **Local apps** and open **MeshBeacon**. If it does not appear, reload the page; check
   that the path is `<local apps folder>/meshbeacon/config.yaml` and look at *Settings → System → Logs*
   (Supervisor) for a configuration error.
3. Select **Install**. Home Assistant builds the image on the device. On a Raspberry Pi 4 this
   takes several minutes. If the build fails, the Supervisor log shows the failing step.
4. On the **Info** tab, leave **Start on boot** on and switch **Watchdog** on (recommended: it only
   restarts MeshBeacon if MeshBeacon itself stops responding, never because the internet is down).

## 4. First start (no peers)

1. Select **Start** and open the **Log** tab. Within about a minute you should see:

   ```text
   [meshbeacon] MeshBeacon 0.1.0 starting (Reticulum 1.6.0, aarch64).
   [meshbeacon] Transport mode: off.
   [meshbeacon] Node identity: created a new identity for this node.
   [meshbeacon] ⚠ MeshBeacon is running, but it is not connected to anyone. ...
   ```

2. That warning is expected: with no peers, MeshBeacon makes no connections.
3. On the **Info** tab, the security rating should be shown; record it (target: 8).

## 5. Connect to a peer you choose

1. Open the **Configuration** tab. Under **Your own peers**, add an entry:
   - **name**: any label, for example `Test peer`
   - **host**: the peer's address (hostname or IP address)
   - **port**: the peer's TCP port (often `4242`)
   - **network name** / **passphrase**: only if the peer's operator gave you them
2. **Save**, then **Restart** the app.
3. In the **Log** tab, look for `Connected to Test peer. Your node is online.`

For the first milestone, use a peer you control or trust (for example another Reticulum node of
your own reachable over your LAN or tailnet). Connecting to public infrastructure was not part of
the automated testing; the operator of any peer can see your public IP address.

## 6. Optional: transport mode

Switch on **Share my connection with others (transport mode)**, save and restart. The log shows
`Transport mode: on — sharing your connection with others.` Only leave it on if your internet plan
has data to spare.

## 7. What to record for the review

Without any household identifiers (no IP addresses, hostnames, SSIDs or identity hashes):

| Item | Where |
|---|---|
| Installation succeeded, build time | Info tab, your clock |
| Security rating shown | Info tab |
| Log lines from first start and after connecting | Log tab (remove hostnames before sharing) |
| Idle memory | The app's **Info** tab shows its RAM usage; note it after about an hour. (Do not disable the SSH app's protection mode to use Docker commands for this.) |
| "Connected" message, and reconnection after restarting the peer | Log tab |
| AppArmor: any denials | *Settings → System → Logs*, Host log, search for `apparmor` and `meshbeacon` |

## 8. Updating or removing

- **Update:** replace the contents of `<local apps folder>/meshbeacon/` with the new version, then *App store →
  ⋮ → Check for updates* and **Rebuild** on the app page. Your node identity is kept.
- **Uninstall:** *Uninstall* on the app page. This **deletes the app's data, including the node
  identity**, unless you have a backup.
- **Restore:** restore the app (or a full backup) from *Settings → System → Backups*; the identity
  is restored with it and verified on the next start.

## 9. If something goes wrong

| What you see | What to do |
|---|---|
| ⚠ cannot reach any of your peers | Check the host and port, and that the peer is running. MeshBeacon keeps retrying. |
| ✖ some options need correcting | Fix the listed fields in the Configuration tab. |
| ✖ has paused to avoid a restart loop | Wait until the time shown, then restart, or change any option. |
| ✖ … identity … has NOT created a new one | Restore the app from a backup (section 8). |
| Build fails | Check the Supervisor log; a network problem during the build is the usual cause. |

Report security problems privately (see `SECURITY.md`), not in public issues.
