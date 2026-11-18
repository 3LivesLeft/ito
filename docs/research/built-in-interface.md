# A built-in MeshBeacon interface: validation of the Ingress architecture

**Status: validation before implementation.** Nothing here is implemented. The proposal is
[ADR 0013](../adr/0013-built-in-interface-ingress.md) (proposed). It follows the maintainer's
permanent principle of out-of-the-box usability ([vision](../vision.md), principle 2,
18 Nov 2026).

## 1. The requirement

| # | Requirement | Source |
|---|---|---|
| R1 | The dedicated interface comes with the standard app installation: no separate integration, HACS or dashboard set-up | Maintainer |
| R2 | A sidebar entry and supported HA authentication | Maintainer |
| R3 | Install, configure and start within five minutes, with no terminal and no YAML | Maintainer, vision |
| R4 | The integration remains an optional enhancement (entities, dashboards, statistics, automations) | Maintainer |
| R5 | No duplicated monitoring logic; no unnecessary resource use | Maintainer, vision principle 10 |
| R6 | No compromise of the existing security and privacy principles | Maintainer, vision principles 5–6, CLAUDE.md rule 4 |

**The v0.2 state fails R1.** The sidebar panel of [ADR 0007](../adr/0007-sidebar-panel.md) lives
in the custom integration. The integration must be copied into `/config/custom_components` by
hand, or installed through HACS, and then added.

## 2. Candidates

| | **A. Supervisor Ingress (app-served UI)** | B. Integration panel (ADR 0007) | C. App installs the integration for the user | D. App creates a dashboard |
|---|---|---|---|---|
| Comes with the app (R1) | **Yes** | No | Needs write access to `/config` (`homeassistant_config` mapping) | Needs `homeassistant_api` |
| Sidebar and HA login (R2) | **Yes**: Supervisor-authenticated, `panel_icon`, `panel_title`, `panel_admin` | Yes | Yes, after a restart | Yes |
| New app permissions | **None.** One internal listener reachable only by the Supervisor | None | Write access to HA's configuration: **rejected** (rule 4; architecture §8 "no write access to the Home Assistant configuration directory") | Full HA API: **rejected** |
| Works without the integration | **Yes** | No | — | — |

**Only A satisfies R1 without a new permission.** C and D break R6 outright. B remains useful
only as part of the optional integration, but two dedicated UIs would duplicate code and confuse
users (§6).

## 3. How Ingress works (what is verified and what is not)

| Fact | Status |
|---|---|
| The Supervisor authenticates the HA user and proxies requests to the app's `ingress_port`. The app sees requests only from the Supervisor at **172.30.32.2** and must refuse every other source | **[Verified, secondary]**: HA's developer guide, as quoted in search results ([HA guide](https://contributors.home-assistant.io/apps/guides/ingress/)); the primary page is blocked by this session's network policy |
| The Supervisor **strips** `X-Ingress-Path` and the `X-Remote-User-*` headers from client requests and sets them itself. They are trustworthy **only** if the source check holds; the user headers are not guaranteed | **[Verified, secondary]**: as above |
| Real projects were bypassed when they trusted ingress headers without the source check (for example GHSA-v8q4-3m6w-r576 in Tesserae; an add-on terminal reachable by other add-ons) | **[Verified]**: [tesserae#580](https://github.com/dmellok/tesserae/pull/580), [ha-addon-claude-code#9](https://github.com/Tom-Joad/ha-addon-claude-code/pull/9) |
| Ingress does **not** change the security rating for MeshBeacon: the +2 is for "Ingress *or* no host network and no published ports", which MeshBeacon already has. **The rating stays at 8** | **[Verified]** earlier from Supervisor source, `supervisor/apps/utils.py` `rating_security`, `e610ca8` ([feasibility](feasibility.md) §app options) |
| The Supervisor connects to the app over **plain HTTP**. No TLS upstream is offered | **[Assumption]**, from memory of Supervisor's ingress proxy (`supervisor/api/ingress.py`). **Verify before implementing (V-1)** |
| Whether the Supervisor forwards the user's **ingress session cookie** to the app | **[Open] (V-2)**. This matters because of §4 |
| The app page's "Show in sidebar" switch is **off** by default for a newly installed app; "Open web UI" works without it | **[Assumption] (V-3)**. If true, the five-minute path includes one switch (§5) |
| Ingress pages run in an iframe on HA's own origin, so the page can follow HA's theme by reading the parent document's CSS variables, and `prefers-color-scheme` otherwise | **[Assumption] (V-4)** |
| Ingress works in the HA companion apps (iOS and Android) | **[Assumption] (V-5)**, widely used by other apps |
| The app can switch "Show in sidebar" on itself only through the Supervisor API (`hassio_api`) | **[Assumption]**. **Not proposed**: no Supervisor API access (rule 4) |

## 4. Security analysis

### 4.1 The plain-HTTP question

v0.2 moved the status API to TLS because another app on the Supervisor's internal network keeps
`NET_RAW` by default and can ARP-spoof ([threat T34](../security/threat-model.md), verified). If
Ingress is plain HTTP (V-1), the same attacker could read or alter **Supervisor ↔ MeshBeacon**
ingress traffic.

| Asset on the ingress path | Exposure to a malicious, `NET_RAW`-holding app performing active spoofing | Acceptable? |
|---|---|---|
| Status figures and peer names (the same as the entities) | Readable | **Only if** the ingress UI carries nothing more sensitive than the v0.2 snapshot, with no hashes, hosts, keys or tokens. That was already the bar for option D in v0.2 review, and it was rejected *for an unauthenticated listener reachable by every app*. Ingress narrows this to active spoofers only, through the source check |
| Integrity of what the user sees | Alterable (misleading display, T33) | Accept for read-only figures; never for actions |
| **Any action** (write, configuration change, sending a message) | Forgeable | **No.** The ingress interface is read-only. Writes stay on the pinned-TLS, key-authenticated path ([ADR 0010](../adr/0010-home-assistant-messaging-interface.md), proposed for v0.3) or in the Supervisor's own Configuration tab |
| HA user's ingress session cookie (V-2) | If the Supervisor forwards it, it could be captured. **[Assumption]** HA ingress sessions are not tied to one app, so a captured session could open **other** apps' ingress UIs | **Blocking until V-2 is answered.** This is a general Home Assistant property, not one MeshBeacon creates, but enabling Ingress adds MeshBeacon's traffic to what can be sniffed. If the cookie is forwarded, the maintainer must decide with that fact in hand |

**[Recommendation]** Proceed only with: read-only Ingress; the v0.2 snapshot as the only data;
the source check enforced on the socket's peer address (never on forwarded headers); and V-1 and
V-2 answered from Supervisor source before implementation. Document the Supervisor's
`app_drop_net_raw` hardening option for users who want to close the spoofing route entirely.

### 4.2 Controls (proposed)

| Control | Detail |
|---|---|
| Source check | Refuse any connection whose peer is not `172.30.32.2` (403, counted, not logged per request). Configurable only for tests |
| Read-only | `GET` only; every other method gets 405. No query parameter changes state |
| No secrets | No API token, Supervisor token, discovery data, certificate, hash, host or port in any response or page |
| Headers | `Content-Security-Policy: default-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` for data |
| Paths | Fixed routes only; static files from an in-memory map built at start (no filesystem lookup per request, so no traversal) |
| Bounds | The existing `BoundedHTTPServer`: ≤ 4 connections, 5 s inactivity timeout, 10 s deadline |
| Admin only | `panel_admin: true` (consistent with ADR 0007) |
| Identity headers | `X-Remote-User-*` are not used and not logged |
| Same page rules as ADR 0007 | `textContent` only; no third-party code, CDN, `eval` or browser storage (the existing tests move with the code) |

## 5. The five-minute path with Ingress (no terminal, no YAML)

| Step | User action | Budget |
|---|---|---|
| 1 | Click the README's "Add repository" My Home Assistant link, then confirm | 0:30 |
| 2 | Install MeshBeacon | 1:30 |
| 3 | Configuration tab: choose a peer (preset, or host and port in the form) and save | 1:00 |
| 4 | Start | 0:15 |
| 5 | Switch on **Show in sidebar** (V-3), or press **Open web UI** | 0:15 |
| 6 | MeshBeacon's interface shows "Online — connected to Emerald" | 0:30 |
| | **Total** | **≈ 4:00** |

The optional integration is offered from inside the interface, with one card: "Want MeshBeacon
in your dashboards and automations?". It links to the guide and is never required.

## 6. Avoiding duplication

| Concern | Proposal |
|---|---|
| Monitoring logic | **None new.** The core's `Collector` already runs whether or not the integration is on (only publishing to the API is gated). The UI endpoint serves `build_snapshot()`, the same function the status API uses |
| History | The core has only 60 s rate windows. **[Recommendation]** a bounded, **memory-only** ring: 24 h at 5-minute resolution, 10 series. It is never written to disk (no SD wear) and is lost at restart ("since the app started"). With the integration installed, long-term history and statistics stay in HA's recorder, as now. Measured below |
| Two dedicated UIs | **[Recommendation]** Withdraw the integration's sidebar panel (ADR 0007, never released) and move its code into the app as the single dedicated UI. The pure `model.js` and the rendering code are reused; only the data source changes (app JSON instead of `hass.states`). The integration returns to entities, repairs and diagnostics only. This removes the duplicate sidebar entry and one code path |
| Charts across 7 days | Not available from the app's 24-hour ring. They remain available through the integration (recorder statistics) and native dashboards. **Maintainer decision (D3):** accept 24 h in the built-in UI, or extend the ring to 7 days at 1-hour resolution (+168 rows, about 45 KB, see below) |

## 7. Measurements (throwaway spike, amd64 sandbox; not Pi figures)

A scratch script used the core's own `BoundedHTTPServer`, outside the repository.

| Measure | Result | Budget |
|---|---|---|
| History ring, 24 h × 5 min, 10 series (288 rows), traced allocation | **≈ 74 KB** (≈ 28 KB as JSON) | ≤ 256 KiB |
| 7-day extension, 1 h resolution (168 rows) | **≈ 45 KB** (estimated from the above, the same row shape) | — |
| Extra listener in the core process, after 600 requests | **≈ 1.2 MiB** RSS | ≤ 4 MiB |
| CPU per request (snapshot + 24 h history, or a 40 KB static file) | **≈ 1.1 ms** | — |
| Polling every 10 s while the page is open | **≈ 0.011 %** of one core; zero when closed | ≤ 0.1 % on the Pi |
| Request from a source not on the allow-list | **403** | Refused |

**[Assumption]** A Raspberry Pi 4 is 3–6× slower per request, so polling would stay under
0.07 % of one core. This is to be measured on the Pi (UI-9).

## 8. Validation still required before implementation

| ID | Question | Method |
|---|---|---|
| V-1 | Ingress upstream protocol (HTTP only?) | Read Supervisor's ingress proxy source at a pinned commit. Not read in this session: the Supervisor repository is outside this session's repository scope, and HA's developer docs are blocked by its network policy |
| V-2 | Is the ingress session cookie forwarded to the app? Are ingress sessions app-scoped? | Supervisor source; confirm on the Pi by logging header **names** only (never values), with approval |
| V-3 | "Show in sidebar" default | Pi, during the hardware run, after approval |
| V-4 | Theme following inside the iframe | Pi, browser and companion app |
| V-5 | Companion app behaviour | Pi, phone |
| V-6 | Memory and CPU on the Pi (UI-8, UI-9) | Pi |

## Sources

- HA developer guide on ingress (quoted via search; the primary page is blocked here):
  [contributors.home-assistant.io/apps/guides/ingress](https://contributors.home-assistant.io/apps/guides/ingress/).
- [Tesserae security fix #580](https://github.com/dmellok/tesserae/pull/580) (ingress header bypass);
  [ha-addon-claude-code #9](https://github.com/Tom-Joad/ha-addon-claude-code/pull/9) (source restriction).
- Supervisor `rating_security`, `e610ca8`, as verified in [feasibility](feasibility.md).
- Community notes on the rating: [Add-on security calculation](https://community.home-assistant.io/t/add-on-security-calculation/269497).
