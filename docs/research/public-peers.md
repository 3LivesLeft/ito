# Public peer presets

Status: **Research (Phase 0 amendments)** · Research date: 18 November 2026
Decision record: [ADR 0004](../adr/0004-public-peer-presets.md)

Labels: **[Verified]**, **[Assumption]**, **[Recommendation]**, **[Open]** (see
[feasibility.md](feasibility.md#how-to-read-this-document)).

## 1. Why presets

The ease-of-use goal (a non-technical user connected within five minutes — see
[first-run UX](../ux/first-run.md)) is hard to meet if the user must first find, judge and type in
a Reticulum peer address. A short list of well-known public entry points, chosen with one click,
removes that step. It must not compromise the privacy requirements:

- no external connection by default;
- an explicit opt-in;
- manual custom peers always available;
- no dependency on any single provider;
- a plain explanation of what a public peer can see;
- endpoints verified before they are shipped.

## 2. Candidate endpoints

### 2.1 Ratspeak servers

**[Verified]** from Ratspeak's documentation repository `ratspeak/ratspeak-docs` at
`f3c5318d392671dac659c795bbcab5d6d442ac16` (2026-11-17), `docs/networking/ip-internet-and-i2p.md`
§"Public Ratspeak TCP servers" and `docs/reference/troubleshooting.md`:

| Name | Endpoint | Interface type | Documented rules |
|---|---|---|---|
| **Ruby** | `1.ratspeak.org:4141` | `TCPClientInterface` | None stated |
| **Emerald** | `2.ratspeak.org:4242` | `TCPClientInterface` | None stated; `rns.ratspeak.org:4242` is a legacy alias |
| **Diamond** | `3.ratspeak.org:4343` | `TCPClientInterface` | "Having 50 remote peers connected through you, or more than 20 connections from the same IP address, gets you banned: 24 hours the first time, 7 days the next, and 30 days each time after that." |

Ratspeak describes them as "best-effort public Ratspeak infrastructure with no uptime guarantee",
and states that a transport server "cannot decrypt private LXMF message content, but it can
observe its own connections"; for community servers it adds "Their operators can see your IP
address" — which applies equally to Ratspeak's own servers.

**[Verified]** Ratspeak's own app and docs target **rsReticulum** (Rust) and say its examples
"follow Reticulum 1.6.0". Ratspeak is operated by Ratspeak LLC (per rsReticulum's licence header).

**Not verified:**

- **[Open]** which software and version the servers run, and therefore whether Python RNS 1.6.0
  interoperates with them reliably (feasibility Q-13);
- **[Open]** whether the hostnames resolve and the ports accept connections today — DNS lookups
  for all four hostnames failed from the research environment, which has restricted outbound
  networking, so this says nothing about the servers themselves;
- **[Open]** Ratspeak's data-retention or logging policy for these servers. `ratspeak.org` could
  not be reached from the research environment;
- **[Open]** whether Ratspeak is content for a third-party project to list its servers as presets.

**Re-checked 20 November 2026** at `91435d956e66607bd40d3f478067d9380c5670ec` (2026-11-18, "Note
Diamond's stricter limits"): the endpoints and Diamond's rules are unchanged; the same document
still gives a `TCPClientInterface` block with only `target_host` and `target_port`, so **no IFAC
network name or passphrase** is required **[Verified]**.

### 2.1a ReticulumNet (Reticulum Netherlands)

| Name | Endpoint | Interface type | Documented rules |
|---|---|---|---|
| **ReticulumNet** | `node.reticulumnet.nl:4242` | `TCPClientInterface` | None stated; "public and open to new people"; transport and propagation node |

- **[Verified, indirectly]** The endpoint, interface type and access statement are from the
  operator's site, `https://www.reticulumnet.nl/en/get-started/` (with `/community/` and
  `/on-the-map/`), as indexed by a web search on 20 November 2026. The research environment could
  not resolve `reticulumnet.nl`, so the page was not read directly. The endpoint also matches the
  one supplied by the maintainer.
- **[Verified, indirectly]** No IFAC network name or passphrase appears in the published stanza.
- **[Open]** Operator identity beyond the site name, logging policy and consent to be listed (V1).
- **[Open]** V2–V7, as for every preset.

### 2.2 Other public entry points

**[Verified]** The Reticulum manual mentions `amsterdam.connect.reticulum.network`
(`BackboneInterface`, port 4251, as a configuration example in `interfaces.rst`),
`dublin.connect.reticulum.network:4965` (as sample output, labelled "RNS Testnet Dublin", in
`using.rst`) and `sideband.connect.reticulum.network:7822` (as sample output). These are examples
in documentation, not a maintained directory. Ratspeak's docs point to
`reticulum.network/connect.html` for current information; that page could not be fetched from the
research environment.

**[Verified]** The manual itself recommends *interface discovery* over hard-coded entry points
(`gettingstartedfast.rst`: "a better option is to enable interface discovery and either manually
select relevant, local interfaces, or enable discovered interface auto-connection").

### 2.3 Status of the shipped preset data

| Preset id | Endpoint | Source checked | V1–V7 |
|---|---|---|---|
| `ratspeak_ruby` | `1.ratspeak.org:4141` | 20 Nov 2026 | Not yet (maintainer) |
| `ratspeak_emerald` | `2.ratspeak.org:4242` | 20 Nov 2026 | Not yet (maintainer) |
| `ratspeak_diamond` | `3.ratspeak.org:4343` | 20 Nov 2026 | Not yet (maintainer) |
| `reticulumnet` | `node.reticulumnet.nl:4242` | 20 Nov 2026 (indirect) | Not yet (maintainer) |

The maintainer records each V1–V7 result by setting `release_checks_passed_on` in `networks.json`;
`tools/check_release.py` refuses a release tag until every listed preset has one (remove a preset
that fails).

## 3. Interoperability and verification requirements

**[Recommendation]** A preset may only be shipped in a release if **all** of the following were
recorded, by a human, within the 30 days before that release:

| # | Check | How |
|---|---|---|
| V1 | Operator identified and willing to be listed | Written confirmation, or at minimum their public documentation listing the endpoint for general use |
| V2 | Endpoint resolves and accepts TCP | From the maintainer's own network |
| V3 | Python RNS (the exact pinned version) connects with `TCPClientInterface` and stays connected ≥ 24 h | `rnstatus -j` shows the interface up; reconnects after a forced drop |
| V4 | Paths are learnt through the peer | `rnpath` resolves at least one well-known destination via it |
| V5 | End-to-end reachability | `rnprobe` to a test destination controlled by the maintainer on a *different* connection, through the peer |
| V6 | No unexpected behaviour | No IFAC mismatch, no repeated disconnects, no ban when used with MeshBeacon's defaults |
| V7 | Rules documented | Any operator rules (for example Diamond's limits) shown to the user before they choose it |

These tests touch live public infrastructure, so they are **manual release checks performed by
the maintainer**, not automated CI tests — CI never connects to live networks
([testing strategy](../testing/strategy.md)).

The verification record lives in the repository (`presets/verification.md`, proposed) with date,
RNS version, tester and results.

## 4. Privacy implications to explain to users

Shown in plain language in `DOCS.md` and in the option's description, before connecting:

> **Connecting to a public peer**
> A public peer is a computer run by someone else that links your MeshBeacon node to the wider
> Reticulum network.
> - **They can see your home's public IP address**, when you are connected, and how much data
>   passes through the connection.
> - **They cannot read** your end-to-end-encrypted Reticulum messages.
> - They may keep logs. MeshBeacon cannot control what an operator records.
> - They may go offline at any time, and may ban connections that break their rules.
> - Using a public peer is optional. You can instead connect only to people you know, or to your
>   own nodes over your own network or Tailscale.

## 5. Interaction with transport mode

**[Verified]** Diamond bans nodes with "50 remote peers connected through you" — i.e. it is aimed
at nodes acting as hubs. **[Recommendation]** If transport mode is enabled together with the
Diamond preset, MeshBeacon shows a warning; if a TCP listener is ever added (not in v0.1), the
combination should be refused or capped.

## 6. Recommendation

1. **Offer presets**, but ship an **empty preset list until V1–V7 are complete** for at least two
   independent operators. Shipping presets from only one operator would make that operator the
   de-facto default provider.
2. Ratspeak Ruby, Emerald and Diamond are **candidates**, not yet approved presets.
3. Seek at least one **non-Ratspeak** candidate — for example a community entry point listed on
   the Reticulum project's connect page, once fetched and verified.
4. Store presets as **data** (a versioned file of name, operator, host, port, interface type,
   rules, verification date), so they can be added, corrected or removed without code changes, and
   so users can see exactly what each preset does.
5. **Default: none selected.** A user may select zero or more presets *and* add custom peers.
6. Revisit **interface discovery** (receive-only listing, user chooses, never auto-connect) as a
   provider-neutral alternative after v0.1.0. **[Open] Q-24**: confirm that `discover_interfaces`
   only listens and never transmits anything about the local node.
