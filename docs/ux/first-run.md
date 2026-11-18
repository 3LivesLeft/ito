# First-run experience and configuration design

Status: **Proposed (Phase 0 amendments)** · Applies to v0.1.0

## 1. Principle

**Ease of use is a core project principle**, equal to privacy and security. When the two seem to
conflict, the answer is a safe default plus one clearly explained choice — not more options.

**Target:** a non-technical Home Assistant user can install MeshBeacon and establish a Reticulum
connection **within five minutes**, without editing a file, opening a terminal or knowing what an
interface is.

## 2. The five-minute path

| Step | User action | Time budget | Notes |
|---|---|---|---|
| 1 | Add the MeshBeacon repository (one-click "Add repository" link in the README) | 0:30 | HA "My" link opens the right dialog |
| 2 | Install the app | 1:30 | Image download over 5G; size target ≤ 80 MB compressed (**[Assumption]** — measure in Phase 1) |
| 3 | Open **Configuration**, choose a connection | 1:00 | Either tick a preset, or enter a peer's host and port |
| 4 | Read the one-paragraph privacy notice shown in the option description | 0:30 | |
| 5 | Start the app | 0:15 | |
| 6 | Open **Log** and see a plain summary: "Connected to Emerald. Your node is online." | 0:30 | Connection normally completes in seconds (verified ~5 s on loopback including a retry) |
| | **Total** | **≈ 4:15** | 45 s contingency |

If no verified presets are available yet (see [ADR 0004](../adr/0004-public-peer-presets.md)),
step 3 becomes "copy a peer address from the documentation", adding about a minute. The target is
then tight but achievable; measuring it with real users is part of v0.1.0 acceptance.

## 3. Configuration options (v0.1.0)

Few options, plain names, safe defaults. Illustrative only — not an implementation.

| Option (UI label) | Type | Default | Notes |
|---|---|---|---|
| **Public peers** | Multi-select from verified presets | *none* | Description includes the privacy notice. Diamond shows its rules. |
| **Your own peers** | List of { name, host, port, network name (optional), passphrase (optional) } | *empty* | Always available. Passphrase is a `password` field, never logged. |
| **Share my connection with others (transport mode)** | On/off | **Off** | See §4. |
| **Log detail** | quiet / normal / detailed | normal | Maps to RNS log levels 2 / 4 / 5; never higher by default |
| *Advanced:* memory limit (MB) | number | 256 | Self-imposed; see architecture §4.2 |
| *Advanced:* monthly data warning (GB) | number | 0 (off) | Warning only in v0.1 |

Not in v0.1.0: TCP listener, LAN discovery (`AutoInterface`), interface discovery, I2P, RNode,
raw RNS configuration.

## 4. Transport mode, explained to the user

Option description (draft):

> **Share my connection with others (transport mode)**
> When this is **off** (recommended for most people), your node uses the network but does not
> carry other people's traffic.
> When this is **on**, your node also passes traffic between other Reticulum users, which helps
> the network grow. Only turn it on if your Home Assistant is always on and your internet plan
> has data to spare: on a busy network this can use a noticeable amount of data. Some public peers
> limit how many people may connect through you.

**[Verified]** behaviour to document truthfully: with transport off, RNS uses an *ephemeral*
network-facing transport identity that changes on each start (feasibility §7.1); with transport
on, the stored identity is used and stays the same. MeshBeacon persists and protects the stored
identity either way.

## 5. Plain-language status messages

The app log is the v0.1 user interface. Messages are written for people, with the technical
detail on the next line.

| Situation | Message (draft) |
|---|---|
| Started, no peers configured | ⚠ "MeshBeacon is running, but it is **not connected to anyone**. Add a public peer or one of your own peers in the Configuration tab." — repeated every 6 hours, not every minute |
| Peers configured, none reachable | ⚠ "MeshBeacon is running, but cannot reach any of your peers. Check your internet connection. It will keep trying automatically." |
| Some peers up | "Connected to 1 of 2 peers (Emerald). Your node is online." |
| Recovering | "The Reticulum service stopped unexpectedly and has been restarted (attempt 2)." |
| Circuit breaker open | ✖ "The Reticulum service keeps failing. MeshBeacon has stopped retrying for 15 minutes. See the lines above for the cause." |
| Identity problem | ✖ "Your node's identity file is damaged. MeshBeacon has **not** created a new one, because that would change your node's address. To restore from backup, see the documentation; to start fresh, turn on *Advanced: replace identity*." |

**[Verified] limitation:** without `homeassistant_api` or `hassio_api` (which v0.1 deliberately
does not request), the app cannot raise a Home Assistant notification or repair issue. The log
and the app's started/stopped state are the only v0.1 signals. The v0.2 integration will surface
the same states as entities and repair issues.

## 6. Diagnostics (v0.1)

- A startup report in the log: MeshBeacon version, RNS version, architecture, transport on/off,
  configured peers (names and hosts only), and the health state.
- A periodic status line (default every 30 minutes): peers up/down, bytes sent/received since
  start, memory use.
- No identity hashes, passphrases, tokens or key material in any of these.

## 7. Measuring ease of use

v0.1.0 acceptance includes a **timed first-run test** by at least three people who have not used
Reticulum before, on a fresh HA install, recording time and every point of confusion. Target:
median ≤ 5 minutes, nobody over 10 minutes.
