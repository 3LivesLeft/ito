# ADR 0013: The built-in MeshBeacon interface, served through Supervisor Ingress

- **Status:** **Proposed — validation in progress.** Not to be implemented until V-1 and V-2 are
  answered and the maintainer approves. If accepted, it **supersedes ADR 0007** (the
  integration's panel, never released) and amends ADR 0006 and the v0.2 review's rejection of
  option E.
- **Date:** 18 November 2026
- **Driver:** the permanent principle of out-of-the-box usability ([vision](../vision.md),
  principle 2).
- **Evidence:** [validation of the Ingress architecture](../research/built-in-interface.md),
  [threat model T59–T64](../security/threat-model.md)

## Context

MeshBeacon's own interface must come with the standard app installation. The ADR 0007 panel
needs the custom integration to be installed by hand or through HACS. The v0.2 review rejected an
Ingress UI because it would have been "a second monitoring implementation, with its own history
and charts". This ADR shows how to avoid that, and sets the security conditions.

## Decision (proposed)

1. **Ingress.** `config.yaml` gains `ingress: true`, `ingress_port: 8097` (not 8099, which is the
   watchdog's health port), `panel_icon: mdi:lighthouse-on` (the brand icon, [branding](../branding.md)), `panel_title: MeshBeacon` and
   `panel_admin: true`. **No other permission changes.** The security rating stays at 8
   (verified rating rule).
2. **Listener.** The core serves the UI with the existing `BoundedHTTPServer`, which is always on.
   It accepts connections only from `172.30.32.2`, checked on the socket peer address, and allows
   `GET` only. It uses fixed routes and an in-memory static map, carries the security headers in
   the validation record (§4.2), and serves no secrets.
3. **Data.** One endpoint returns `build_snapshot()` (the existing function; no new metrics logic)
   plus a **memory-only** history ring: 24 h at 5-minute resolution, 10 series, ≈ 74 KB measured.
   Nothing is written to disk.
4. **One UI codebase.** The ADR 0007 panel code moves into the app. `model.js` is unchanged; a
   small data adapter replaces `hass.states`/`callWS` with relative `fetch` calls to the app,
   which are same-origin under the ingress path. The integration's own panel is withdrawn before
   release. The integration keeps entities, repairs and diagnostics, and stays optional.
5. **Read-only, permanently, on this path.** No action of any kind goes through Ingress while the
   Supervisor → app hop is plain HTTP. Configuration stays in the Supervisor's Configuration tab;
   future writes use the pinned-TLS, key-authenticated API (ADR 0010).
6. **Pages follow ADR 0007's rules:** `textContent` only, no third-party code or CDN, no browser
   storage. The tests move with the code. The page refreshes every 10 s only while visible.

## Maintainer decisions requested

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Approve an always-on, Supervisor-only, read-only Ingress listener, once V-1 and V-2 are answered | Approve, conditionally |
| D2 | Withdraw the integration's panel (ADR 0007) in favour of the single built-in UI | Withdraw |
| D3 | History in the built-in UI: 24 h (≈ 74 KB) or 24 h plus 7 days at 1 h (≈ 120 KB in total) | 24 h now; 7 days stays available through the integration |
| D4 | Admin-only sidebar entry (`panel_admin: true`) | Keep admin-only |

## Consequences

- The five-minute path ends in MeshBeacon's own interface, with no integration needed (§5 of the
  validation).
- One more always-on internal listener: ≈ 1.2 MiB RSS measured, with zero CPU when the page is
  closed. It is covered by the AppArmor and container tests (`ingress` currently fails
  `tests/unit/test_app_config.py`; that test changes only with this ADR's approval).
- Residual risk **RR-9**: an installed malicious app holding `NET_RAW` that actively spoofs could
  read or alter the read-only figures on the Supervisor → app hop. This is mitigated by the source
  check, read-only operation and no secrets. Users can close the route with the Supervisor's
  `app_drop_net_raw` option.
- If V-2 shows that the Supervisor forwards a usable session cookie over plain HTTP, this ADR
  returns to the maintainer before any implementation.
