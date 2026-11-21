# ADR 0026: bundle the dashboard and setup in the app

Status: **Accepted by the maintainer, 21 November 2026.** Supersedes the Ingress block in ADR
0013 and the mandatory two-part dashboard installation in ADR 0015. The maintainer explicitly
approved Ingress, a default sidebar entry and configuration in the dashboard.

## Decision

The app is the primary installation route. It serves the shared ito interface through Supervisor
Ingress on internal port 8097. No published port, host networking, new capability or broad
Supervisor/Core API permission. Home Assistant authenticates Ingress; `panel_admin: true` restricts
it to administrators. The app accepts only the actual Supervisor socket peer `172.30.32.2`, never
an address supplied in forwarding headers. It also requires the Supervisor-authenticated
`system-admin` user group header (Supervisor 2026.11+); missing or non-admin groups are refused. This follows the official
[Ingress guide](https://contributors.home-assistant.io/apps/guides/ingress/).

**Accepted limitation:** the Supervisor-to-app Ingress hop is plain HTTP on the internal network.
This is not end-to-end TLS, and an attacker able to intercept that network remains a risk. This
replaces the earlier decision to block Ingress. The optional integration retains its pinned TLS.
No private security-report details are published here.

The app adds its own sidebar entry once after a successful start, recording success in its data
folder. Later user choices to hide it are respected. The dashboard is always available through
Open Web UI, independent of the optional integration or discovery.

Configuration goes through fixed `/addons/self/info`, `/addons/self/options/config`,
`/addons/self/options` and `/addons/self/restart` operations. These need no extra permission
([Supervisor self API](https://contributors.home-assistant.io/apps/supervisor-api/),
[options reference](https://contributors.home-assistant.io/apps/supervisor-api/apps/)). The existing
root socket relay admits only the four new typed operations. Older Supervisors use the existing
internal token transport; a missing socket relay never falls back to a token. Settings are stored
by Supervisor, so there is no competing configuration file. Every change passes the existing
core validator; stale forms are rejected. Untouched `!secret` references survive. Password values
are omitted from the browser response; retaining, replacing and clearing them are explicit.
Identity replacement is deliberately excluded from this ordinary settings endpoint.

Save and apply responds before requesting an app restart. Supervision shuts down messaging before
Reticulum as before. The browser watches a per-start identifier, reconnects and reports failed or
slow restarts. Configuration requests never run on the health/supervision loop.

Messaging uses the existing engine forwarder, allow-list, rate limits and persistent queue,
contacts and history. The browser reuses the existing draft, pagination and send-idempotency
model. Polling is bounded and stops while hidden. No message data is written to browser storage.

The frontend is generated into the Docker context by `tools/sync_frontend.py`; CI rejects drift.
All asset URLs include a content fingerprint covering the entire tree. HTML/API responses are
`no-store`. An open dashboard reloads on a changed bundle, or offers Load update while editing
settings or holding a message draft. No service worker or separate dashboard update is needed.

## Compatibility

Slug, domain, data paths, entities and existing HTTP/websocket contracts stay unchanged. Updates
reuse the installed app and all existing identities. The optional integration is still useful for
entities, automations and recorder history. Its retained panel is labelled **ito history** when
used with the new app, avoiding two identically named entries after the integration is updated.
An already installed older integration cannot be remotely rewritten by the app: update that
optional integration once if its old sidebar entry remains. No files are copied into HA's config.

The app keeps bounded recent chart samples in memory: 288 five-minute samples and 168 hourly
samples. These restart with the app; existing Home Assistant recorder history remains intact.

## Validation

Unit tests cover self-only calls, validation, secret preservation, conflicts, source-peer checks,
CSRF headers, bounded bodies, asset invalidation, sidebar idempotency and memory bounds. Browser
checks exercise the actual HTTP handler and shared UI with a fake Supervisor and messaging engine.
No tests connect to public Reticulum peers or a household Home Assistant instance. A real
Supervisor installation/update remains a maintainer acceptance check before release.
