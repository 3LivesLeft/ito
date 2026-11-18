# Reference environment

Status: **Confirmed by the maintainer on 18 November 2026** (except where marked).
Used for: hardware, compatibility, soak and recovery testing before each release
([testing strategy §6](strategy.md#6-reference-environment-testing-before-each-release)).

> **Privacy rule.** This document, and anything else in this public repository, must never
> contain the reference installation's private IP addresses, Tailscale addresses or node names,
> MAC addresses, hostnames, SSIDs, public IP addresses, mobile operator account details, Home
> Assistant URLs, Reticulum identity hashes, or any other household-specific identifier. Test
> records use placeholders such as `<lan-ip>`, `<tailnet-ip>` and `<peer-host>`.

## 1. Platform

| Item | Value | Source |
|---|---|---|
| Hardware | Raspberry Pi 4 Model B | Maintainer |
| HA machine type | `rpi4-64` | Maintainer |
| Architecture | **`aarch64`** | Maintainer |
| Installation type | **Home Assistant OS** | Maintainer |
| Home Assistant OS | **18.5** | Maintainer |
| Home Assistant Core | **2026.11.2** | Maintainer |
| Supervisor | **2026.11.0** — reported healthy and supported | Maintainer |
| Docker | 29.8.2 | Maintainer |
| RAM | Believed to be 8 GB — **awaiting confirmation** (Q-30) | Maintainer |
| Storage | 916.2 GB total, 8.1 GB used (SSD) | Maintainer |
| Power | UPS battery backup | Maintainer |
| Uplink | 5G broadband; CGNAT **not yet confirmed** (Q-32) | Maintainer |
| Default network interface | **Wi-Fi** (the original brief assumed Ethernet — Q-31) | Maintainer |

**[Verified]** Supervisor 2026.11.0 (tag `2026.11.0`, `c1c6f0a754c0656eb1af189f11009f1cfc4b3e28`)
has the same watchdog polling interval (120 s, `supervisor/misc/tasks.py`) and the same security
rating function (`supervisor/apps/utils.py`, clamped 1–8) as the commit reviewed in Phase 0. Later
`main` commits change only the Supervisor API socket, which MeshBeacon does not use.

**Q-5 resolved:** the reference device runs a **64-bit Home Assistant OS installation on
`aarch64`**, which is one of the two architectures the Supervisor accepts. The app can run on it;
no 32-bit (`armv7`) build is needed.

## 2. Co-installed apps

| App | Relevance to MeshBeacon | Tests |
|---|---|---|
| **Tailscale** | Possible private path between the user's own Reticulum nodes; the Tailscale app uses host networking **[Assumption]** — confirm on the device. Whether MeshBeacon (bridged network) can reach tailnet addresses is Q-8. | C1–C4 |
| **AdGuard Home** | May act as the household's DNS resolver. Peer hostnames (e.g. `*.ratspeak.org`) are resolved through the Supervisor's DNS plugin, which may forward to AdGuard; a blocklist could block a peer, and AdGuard's query log records peer lookups. | C5–C8 |
| **Matter Server** | Uses host networking and IPv6 multicast **[Assumption]**. MeshBeacon uses neither in v0.1; check that they don't interfere. | C9 |
| **Advanced SSH & Web Terminal** | A high-privilege app: with its protection mode disabled it can reach the Docker daemon and therefore read **any** app's `/data`, including MeshBeacon's identity **[Assumption]** — based on the app's documented behaviour, not verified from its source. This is outside MeshBeacon's control and is documented in the threat model (T26). | Documentation only |
| **File editor** | Maps the HA configuration directory, not app `/data`; MeshBeacon writes nothing there. | — |
| **Get HACS** | Relevant from v0.2 (the integration is distributed through HACS). | v0.2 |

## 3. Implications for MeshBeacon

- **Memory:** with 8 GB (once confirmed) the ≤ 128 MB idle target and 256 MB ceiling are
  comfortable. Defaults must still suit 1–2 GB Pi 4 boards, so they are not raised for this device.
- **Storage:** ample space; storage guards matter for SSD **wear** (log volume and SQLite writes)
  more than capacity. The soak tests record bytes written.
- **Wi-Fi as the default interface:** Wi-Fi drops and reconnections are expected events. They are
  `offline` connectivity, not failures (architecture §4.4), and are part of the outage tests (O1–O5).
- **UPS:** extends runtime but does not remove the risk of an unclean shutdown when the battery is
  exhausted; the power-outage tests (P1–P4) cover both a clean and an abrupt power loss.
- **5G:** data use matters, especially with transport mode enabled; the transport soak (S3)
  records bytes in and out.

## 4. Open items

| ID | Item |
|---|---|
| Q-30 | Confirm RAM (believed 8 GB) — e.g. from *Settings → System → Hardware*; record the figure only |
| Q-31 | Will the reference device move to Ethernet? Testing runs on Wi-Fi either way; repeat on Ethernet if it moves |
| Q-32 | Confirm whether the 5G connection is behind CGNAT. One way: compare the router's WAN address with the public address a website reports, without recording either here |
| Q-33 | Does AdGuard Home serve DNS for the Supervisor/apps on this device, and with which blocklists? |
| Q-8 | Can a bridged-network app reach tailnet addresses through the Tailscale app? |
