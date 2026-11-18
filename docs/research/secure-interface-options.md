# A built-in interface that can safely carry private data and actions

**Status: security review in progress.** The built-in interface through Ingress
([ADR 0013](../adr/0013-built-in-interface-ingress.md)) is **not enabled**. Some findings are
**withheld under responsible disclosure**: they concern Home Assistant's Ingress mechanism in
general, not MeshBeacon's code. They will be summarised here once the disclosure process allows.
This document sets the requirements and compares the options, so that the product is not locked
into read-only operation.

## 1. Decisions (independent architecture review, 18 Nov 2026)

| ID | Decision | Effect now |
|---|---|---|
| D1 | Read-only Ingress approved **on condition** that its security concerns are resolved | **Condition not met.** The review of Supervisor 2026.11.0 confirmed concerns that MeshBeacon cannot mitigate itself (§2). Ingress stays off |
| D2 | Withdraw the integration panel; keep one dedicated MeshBeacon interface | Recorded. **Timing needs confirmation:** withdrawing the panel before a safe built-in interface exists would leave no dedicated interface. Proposal: withdraw it in the same release that ships the built-in interface, so there is exactly one at any time. The panel is unreleased either way |
| D3 | Seven days of bounded, in-memory history | Recorded for the built-in interface: 24 h at 5 min plus 7 days at 1 h (≈ 120 KB), memory only |
| D4 | Admin-only sidebar access | Recorded (`panel_admin: true`; already true for the panel) |
| Product | Users must eventually send and receive LXMF messages from the built-in interface, without a separate integration | Ingress is **read-only for now, not permanently**. Writes and sensitive data wait for a path that meets §3 |

## 2. What the review established (public summary)

- The Supervisor reaches an app's Ingress port over **plain HTTP** on the internal network. **[Verified]**,
  Supervisor 2026.11.0, `supervisor/api/ingress.py`.
- On that hop, requests carry the **user's Home Assistant Ingress session**, which authenticates
  Ingress access. **[Verified]**, same file.
- The Supervisor already treats `NET_RAW` spoofing on that network as a risk (an opt-in feature
  flag removes it). It is **off by default**, and it is set through the Supervisor's options, not
  through MeshBeacon. **[Verified]**, `supervisor/docker/app.py`.
- Ingress pages are shown in Home Assistant's own page context. **[Verified]**, frontend
  20261028.6.

**Consequences for MeshBeacon:**
- **A read-only interface is not a sufficient mitigation.** The exposure concerns the user's
  session and the integrity of what the page delivers, not only what MeshBeacon's endpoints
  allow.
- **MeshBeacon cannot fix this from inside the app.** Any protection the app adds (tokens, request
  signing, in-page encryption) would itself travel over the same unprotected hop.
- The exposure exists for every Ingress app a user opens. Enabling MeshBeacon's Ingress would add
  to it. That conflicts with "no new exposure", so the usability gap is recorded as a defect
  instead ([vision](../vision.md), principle 2).
- Further detail is withheld under responsible disclosure (§5).

## 3. Requirements for private data and authenticated actions in the built-in interface

| # | Requirement |
|---|---|
| S1 | **Confidentiality and integrity end to end**, from the user's authenticated Home Assistant session to MeshBeacon, with no plaintext hop that another app can read or alter |
| S2 | **Trusted code delivery.** The interface's code reaches the browser over a protected path; otherwise any later protection can be removed |
| S3 | **The user's identity is established by Home Assistant** (no separate MeshBeacon login, no passwords in the app) and checked by MeshBeacon for every action |
| S4 | **No new app permissions** that lower the security rating; no published ports by default |
| S5 | **Out of the box**: no separately installed integration, HACS or YAML |
| S6 | **Least privilege**: actions are scoped (for example "send to a known contact"), rate-limited and auditable, as in ADR 0010 |

## 4. Options

| | Meets S1–S2 | S3 | S4 | S5 | Assessment |
|---|---|---|---|---|---|
| **A. Ingress as it is today** | **No** | Yes | Yes | Yes | Read-only would not be enough either (§2). **Not enabled** |
| **B. Ingress after upstream hardening** (session handling and an authenticated, encrypted Supervisor → app hop) | Yes, if upstream provides it | Yes | Yes | Yes | **Preferred long term.** Depends on Home Assistant; pursued through disclosure (§5) |
| **C. User enables the Supervisor's `NET_RAW` hardening flag**, then Ingress | Partly: removes the spoofing route for apps without `NET_RAW`; other privileged apps may still observe traffic **[Assumption]** | Yes | Yes | **No**: an advanced setting outside the app; not discoverable | Documented as optional hardening only; never a precondition we can rely on |
| **D. Integration-delivered interface** (v0.2 panel: browser ↔ HA's authenticated websocket ↔ integration ↔ pinned TLS ↔ app) | **Yes** | Yes | Yes | **No** (the integration is installed separately) | **Secure today.** The current interim interface; meets everything except S5 |
| **E. D, but the integration ships with Home Assistant** (an official core integration) | Yes | Yes | Yes | **Yes** | Meets every requirement, but needs acceptance into Home Assistant Core. Core rarely accepts custom panels, so the UI would move to Home Assistant's own UI building blocks. A human-led upstream contribution (CLAUDE.md rule 10). Long horizon |
| **F. App writes the integration into `/config`** | Yes | Yes | **No**: needs write access to Home Assistant's configuration | Yes | **Rejected** (architecture §8) |
| **G. App serves its own HTTPS port with Home Assistant login (OAuth)** | Yes with a trusted certificate; self-signed certificates cause browser warnings | Yes | **No**: a published port | Partly | **Rejected** by default (posture: no published ports) |
| **H. In-page encryption over Ingress** | **No**: the code that would encrypt arrives over the unprotected hop | — | Yes | Yes | **Rejected** |

## 5. Plan (recommendation)

1. **Now:** Ingress stays off and unimplemented (ADR 0013 blocked). The integration panel stays as
   the interim interface on the unreleased branch until D2's timing is confirmed. Branding work
   continues regardless.
2. **Disclosure:** the maintainer submits the prepared private report to Home Assistant through
   GitHub's private vulnerability reporting for the Supervisor (the channel Home Assistant's
   security policy names), after reviewing it. **Nothing is published or filed publicly without
   approval**, and an AI agent does not post to Home Assistant projects (CLAUDE.md rule 10).
3. **Re-evaluate Ingress (option B)** when Home Assistant responds or ships hardening. ADR 0013's
   condition is then retested from source at the running Supervisor version.
4. **For LXMF messaging in the built-in interface (v0.3):**
   - writes and message content are allowed only on a path that meets S1–S3;
   - until option B exists, sending and receiving stays on the integration's path (ADR 0010);
   - option E is the route to doing it out of the box if upstream hardening does not come.
5. **Never:** options F, G (by default) and H; and never presenting read-only Ingress as a
   mitigation for session exposure.
