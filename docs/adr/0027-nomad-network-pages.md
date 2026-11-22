# ADR 0027: Nomad Network pages — host with the upstream daemon, browse through ito

- **Status:** Proposed for v0.6.0 (implemented on the feature branch; awaiting maintainer review).
  Required by [ADR 0017](0017-independent-node-services.md) decision 5 for any public-facing service.
- **Date:** 22 November 2026
- **Related:** ADR 0005 (bounded recovery), ADR 0014 (engine contract), ADR 0017 (node services),
  ADR 0018 (isolation by user), ADR 0022 (optional services), ADR 0023 (RPC key), ADR 0026 (dashboard)

## Context

v0.6.0 lets a household publish small pages over Reticulum and read other people's pages, also
without internet access. The established format and protocol for this is
[Nomad Network](https://github.com/markqvist/nomadnet): pages written in *micron* markup, served by
a node destination `nomadnetwork.node`, fetched with Reticulum link requests for paths such as
`/page/index.mu`.

Verified against the published `nomadnet` 1.5.0 wheel (PyPI, sha256 `deb9d34d…400b6d`) and RNS
1.6.0, by reading the code where behaviour mattered (file names cited, nothing reproduced) and by
running it on an isolated loopback instance:

| # | Finding |
|---|---|
| F1 | **[Verified]** Licence **GPL-3.0** (wheel `LICENSE`; its PyPI classifier says MIT, the licence file and README say GPLv3). |
| F2 | **[Verified]** 1.5.0 needs `rns>=1.6.0`, `lxmf>=1.3.0` (ito's pins). 1.5.1 needs RNS 1.6.1/LXMF 1.3.1, a separate pin change (D-M4-2). It imports `urwid` at start even in daemon mode (`nomadnet/__init__.py` imports `ui`); `qrcode` only in the text interface. |
| F3 | **[Verified]** `nomadnet --daemon --console --config D --rnsconfig R` runs headless as a client of an existing shared instance and serves files from `[node] pages_path`; a second RNS client fetched `/page/index.mu` and another page over a link (spike, 22 Nov 2026). Resident memory about 55 MB. |
| F4 | **[Verified]** It always starts an LXMF router with a delivery destination for its own identity (`NomadNetworkApp.py`), so anyone who sees the node announce can send that identity LXMF messages, stored in its `storage/`. Propagation is off unless `disable_propagation = no`; periodic sync to an auto-selected propagation node is controlled by `[client] periodic_lxmf_sync`. |
| F5 | **[Verified]** It calls `RNS.Reticulum(configdir=…)` **without** `require_shared_instance`: started while ito's node is down, it would itself become the shared instance, and ito's node would then start as its client. |
| F6 | **[Verified]** A page file with the execute bit is **run** and its output served (`Node.py serve_page`); `*.allowed` files restrict access. New files are picked up every `page_refresh_interval` minutes (minimum 1); deleted files stop being served at once (the request fails). |
| F7 | **[Verified]** A corrupt identity file makes it exit (`nomadnet.panic`); it is never replaced. A missing one is created. |
| F8 | **[Verified]** Node announces carry the node name as UTF-8 `app_data` (`Node.py announce`); an announce without app data was also observed. |
| F9 | **[Verified]** The page browser is part of the urwid text interface; there is no public API to fetch pages for another program. |

## Options

| | A. Upstream daemon for hosting, ito helper for browsing | B. ito serves pages itself with RNS's API | C. A second container / separate app |
|---|---|---|---|
| Compatibility | The reference implementation | A re-implementation of the node's conventions | The reference implementation |
| Project rules | Unmodified upstream as a separate program | Close to "no protocol implementations"; upstream warns against look-alikes | New install step, more ports |
| Install | Same app, no new step | Same app | Breaks "one app" (ADR 0026) |
| Cost | Two Python processes while hosting (~55 MB more) | One process | A whole container |

## Decision

**A.**

1. **One new s6 service, `pages`, as its own user `mb-nomad` (9103)**, started down and controlled
   by the core like messaging (ADR 0018). It runs ito's helper `python -m meshbeacon.pages`, a
   client of ito's shared instance (`require_shared_instance=True`). The helper:
   - **browses**: fetches a page with RNS's public API (`Identity.recall`, `Transport.request_path`,
     `Link`, `Link.request`) — the same request any Nomad Network client makes; F9 leaves no
     upstream alternative;
   - **discovers**: an RNS announce handler for `nomadnetwork.node` keeps a bounded list (500) of
     heard nodes with names, first and last heard; persisted in its own folder;
   - **hosts**: while the user hosts pages, runs the **unmodified upstream `nomadnet --daemon`** as
     its child (same user) and restarts it with back-off. ito never imports `nomadnet` (F1).
2. **Off by default, two steps.** The app option `pages_enabled` (*Nomad Network pages*) starts the
   service after Save and apply; Reticulum then shares its instance, as for messaging. Hosting is a
   separate switch in the **Pages** tab, applied live (no restart), and is off until the user
   switches it on. Disabling either never touches messaging or Reticulum.
3. **The core owns the content.** Pages live in `/data/pages/` (the core's, group `mb-page`):
   drafts only the core can read; published copies in `public/` (0640, never executable) are the
   daemon's `pages_path`. The daemon's user can read them but not change them or add any (F6), and
   AppArmor allows no execution from `/data` either. Page names are `index` or 1–40 of `a-z0-9-`;
   content is UTF-8 text of at most 32 KiB without NUL; at most 50 pages.
4. **The daemon's configuration** is written by the helper at every start with ConfigObj's object
   API from fixed values plus the validated node name, and round-trip checked (rule 12): client
   off, its LXMF address never announced, no periodic sync, no propagation, a stamp cost of 16 and
   a 1 KB limit for messages to it (F4), node announce at start and every 6 hours, page refresh
   every minute, an empty files folder, logging to the console at a level from ito's log option.
5. **Identity.** The daemon's identity (`/data/nomadnet/storage/identity`) is its own, separate
   from Reticulum's and messaging's. The helper creates it the first time with RNS's API and checks
   it before every start; a damaged one stops hosting with a plain message and is never replaced
   (rule 13, F7). Its node address is shown only in the dashboard, never logged (rule 5).
6. **Instance safety (F5).** The core starts the service only once Reticulum is up and stops it
   when Reticulum stops; the helper starts the daemon only while it is itself connected to the
   shared instance, and stops it when that connection is lost. Defence in depth: ito's node now
   exits if it was configured to share its instance and found another program holding it, so the
   core restarts things in the right order instead of running as someone else's client.
7. **Browsing safety.** Remote content is untrusted text. The helper accepts only a 32-hex address
   and a `/page/<name>.mu` path (no `..`), at most 2 fetches at once and 30 a minute, a 30 s limit
   and a 256 KiB answer, and returns plain text. The dashboard renders a safe subset of micron
   (headings, emphasis, alignment, dividers, literal blocks, links) into DOM nodes with
   `textContent` only — no HTML, scripts, styles, colours or images; form fields are shown as
   unsupported. Only Nomad links become buttons, and only into the same viewer: no URL is ever
   followed and nothing is proxied.
8. **Reachability is not claimed.** The dashboard shows *last heard* and whether a path is known
   now; *reachable* only after a fetch succeeded in the last 10 minutes.
9. **Storage bound for F4.** The helper checks the daemon's storage every 5 minutes; above 64 MiB
   it stops hosting and says so. Backups exclude the daemon's cache and resources.

## Consequences

- The image grows by `nomadnet`, `urwid` (LGPL-2.1-only) and `wcwidth` (MIT), about 1.5 MB.
  The GPL-3.0 program is aggregated, as BusyBox and bash already are; it adds to the
  corresponding-source obligation (licensing §5.1, Q-17): its wheel is its source.
- The shared RPC key (ADR 0023) is also readable by `mb-nomad`; the residual risk is T80's.
- A published page can take up to a minute to appear (F6). Media, files, forms and dynamic pages
  are not supported in v0.6.0.
- Moving to nomadnet 1.5.1 waits for the RNS 1.6.1 pin change.

## Review triggers

Any request to run page scripts, serve files or media, accept form input, render colours or
images, follow non-Nomad links, or let the daemon's user write its own pages.
