# Naming research: "MeshBeacon"

Status: **Revised after independent review** · Research date: 18 November 2026
Decision record: [ADR 0003](../adr/0003-name.md)

Labels: **[Verified]**, **[Assumption]**, **[Recommendation]**, **[Open]** (see
[feasibility.md](feasibility.md#how-to-read-this-document)).

The maintainer's stated preference is to **keep the name "MeshBeacon" unless there is a compelling
reason to change**. This document tests that preference.

## 1. The existing MeshBeacon organisation

**[Verified]** by cloning every public repository of the GitHub organisation `MeshBeacon` on
18 November 2026:

| Repository | Purpose | Licence | Commits | First → last commit | Notes |
|---|---|---|---|---|---|
| `MeshBeacon/meshbeacon` ("MeshBeacon Ops") | Offline-first disaster/incident operations console (PHP/Laravel) | Apache-2.0 | 205 | 2026-02-20 → 2026-10-27 | Tagged releases up to **v2.1.9**; CI badges; multi-arch Docker images; 4 stars, 4 forks |
| `MeshBeacon/meshbeacon-mobile` ("CDK Mobile") | React Native companion app for ClusterDuck Protocol nodes | Apache-2.0 | 56 | 2026-02-23 → 2026-10-29 | |
| `MeshBeacon/ots-meshbeacon-plugin` | OpenTAKServer plugin | GPL-3.0 | 10 | 2026-08-25 → 2026-10-09 | |
| `MeshBeacon/openwrt-meshbeacon-package` | OpenWrt package | AGPL-3.0 | 14 | 2026-10-12 → 2026-10-20 | |
| `MeshBeacon/.github` | Organisation profile | AGPL-3.0 | 4 | 2026-08-13 → 2026-10-13 | Links to **meshbeacon.org**, a deployment wiki and a Discord server; has a logo |

Activity and maturity: about **290 commits** across five repositories over nine months,
concentrated in a burst in August 2026 (139 of 205 commits in the main repository); two main
contributor identities; a public website domain; a community chat server. It is a small but
real, actively maintained project with its own brand identity, and it **predates our use of the
name** (our repository's first commit is from November 2026).

### 1.1 Functional overlap

| Dimension | MeshBeacon (existing) | MeshBeacon (this project) | Overlap |
|---|---|---|---|
| Problem space | Communications when infrastructure fails (disaster response) | Communications with or without the internet (households) | **High** |
| Pitch | "keeps working even when the internet doesn't" (org profile) | Former working tagline "Stay connected. With or without the internet." — replaced by "Decentralised connectivity for your home." | **Very high** |
| Radio | LoRa via ClusterDuck Protocol | LoRa via RNode (v0.5) | Medium |
| Protocol | ClusterDuck / MQTT / Cursor-on-Target | Reticulum / LXMF | None |
| Platform | Self-hosted Docker, OpenWrt, mobile app, TAK | Home Assistant app | Low |
| Audience | Emergency responders, operations rooms | Home Assistant users | Low–medium |

### 1.2 Potential for confusion

- **[Verified]** A GitHub search for "meshbeacon" returns the existing organisation first, and its
  repository is called `meshbeacon` — identical to ours.
- **[Assumption]** Users searching for "MeshBeacon mesh offline" will find both projects; support
  requests, issues and reputation (good or bad) may land on the wrong project.
- **[Verified]** The `meshbeacon.org` domain is linked by the existing organisation. We could not
  resolve it from the research environment (outbound DNS is restricted), so its current state is
  unconfirmed.
- Our tagline is close to their pitch, which increases confusion more than the name alone.

## 2. Other uses of the name

**[Verified]** (GitHub search): `salmancuso/MeshBeacon` (MeshCore broadcast scripts for amateur
radio, May 2026); `shimco/meshbeacon` (smart-TV discovery beacon); `bds1337/meshbeacon` (2022,
inactive); `racostacme-come/meshbeacon` (unrelated maths software). **[Verified]** (web search)
"MeshBeacon" is also an Unreal Engine 3 class name and a generic term for Bluetooth "mesh
beacons".

## 3. Trademarks

**[Verified]** A web search for "MeshBeacon" trademark (18 November 2026) found **no** record of
a "MeshBeacon" mark in third-party trademark aggregators. Similar marks exist: RADBEACON
(registered, USPTO), MBEACON (dead, cancelled January 2026), MIBEACON (dead) and many plain
"BEACON" marks.

**[Assumption]** This is **not** a trademark clearance search. The official registers were not
reachable from the research environment and were not searched: UK IPO, EUIPO (eSearch plus),
WIPO Global Brand Database, USPTO, and MyIPO (Malaysia — relevant because the existing
organisation describes its origins in Kelantan, Malaysia).

**[Assumption]** In the UK, an unregistered name can still be protected through the law of
*passing off*, which needs goodwill, misrepresentation and damage. The existing project has some
goodwill, but in a different market (emergency operations) and mainly outside the UK.

## 4. Assessment

| Question | Answer |
|---|---|
| Is there a registered trademark blocking the name? | None found, but the official registers have not been searched. |
| Is there an existing project with the same name in a related field? | **Yes.** Same name, same repository name, overlapping problem space, near-identical pitch, earlier use, own domain and community. |
| Is there a legal reason to change now? | **Not compelling** on current evidence. |
| Is there a practical reason? | **Moderate:** discoverability, mistaken identity, and not owning `meshbeacon.org` or the `MeshBeacon` GitHub organisation. |

**[Recommendation]** **Keep "MeshBeacon"**, as preferred, subject to these conditions — and treat
any of the triggers below as a compelling reason to rename:

1. **Courtesy contact.** Before the first public release, the maintainer contacts the existing
   MeshBeacon maintainers (for example through their Discord or GitHub) to tell them about this
   project and ask whether they object. Record the outcome.
2. **Always disambiguate.** Present the name as *"MeshBeacon for Home Assistant"* in the app
   store, README title, HACS listing and image labels. **[Decision]** app slug `meshbeacon`
   (Q-21 resolved).
3. **Change the tagline** so that it does not echo the existing project's pitch.
   **[Decision]** "Decentralised connectivity for your home." (Q-22 resolved).
4. **Distinct visual identity.** Do not use a logo resembling theirs.
5. **Search the official registers** (UK IPO, EUIPO, WIPO, USPTO, MyIPO) before v0.1.0 is
   published. **[Open] Q-23 — public release gate** (roadmap RG-8).
6. **Credit and link.** README carries a one-line note: *"Not affiliated with the MeshBeacon
   disaster-response project (meshbeacon.org)."*

Rename triggers: the existing maintainers object; a conflicting registered mark is found; or
users repeatedly confuse the projects. Renaming is cheapest before the first published image,
because the slug, image name and `/data` paths are effectively permanent once users install it.
