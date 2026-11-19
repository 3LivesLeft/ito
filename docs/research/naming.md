# Naming research: "MeshBeacon"

Status: **Revised after independent review** · Research date: 18 November 2026 · Reassessed
19 November 2026 for the community direction (§5)
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

## 5. Reassessment for the community direction (19 November 2026)

Prompted by the long-term direction (offline-first community network, LoRa, community alerts and
information). **No rename has been made; this section informs the maintainer's decision (Q-50).**
Not legal advice.

### 5.1 What changed since 18 November

**[Verified]** by GitHub repository search and the organisation's GitHub page, 19 November 2026:

| Finding | Relevance |
|---|---|
| The `MeshBeacon` organisation's tagline is *"Coordinate disaster response over a resilient mesh network."* It now lists LoRa device firmware (`meshbeacon-firmware`, ClusterDuck-based), a LoRa gateway layer (`meshbeacon-uplink`) and a survivor-facing mobile app the page says is on Google Play | They ship off-grid **LoRa** software and a public app under the name |
| A third party publishes `meshbeacon-atak-bridge` ("converts MeshBeacon MQTT events into ATAK Cursor-on-Target") | An ecosystem is forming around their use of the name |
| `salmancuso/MeshBeacon`: automated weather, earthquake and event-alert broadcasting over MeshCore LoRa meshes; a similar `MeshBeaconOKI` project exists | Overlaps proposed v0.5 community information and v0.7 local alerts |
| No registered "MeshBeacon" mark found in general web searches; official registers still not searched (RG-8) | Unchanged |
| Reports of a contested UK trademark application for "MeshCore"; Meshtastic is a registered mark | Name disputes do occur in this ecosystem **[Assumption]** about their outcome |

### 5.2 Overlap, revised

| Dimension | 18 Nov (household framing) | 19 Nov (community direction) |
|---|---|---|
| Problem space | High | **Very high**: communications that keep working without the internet |
| Pitch | Very high (former tagline) | **Very high**: the vision's "continue operating without internet connectivity" echoes their "keeps working even when the internet doesn't" |
| Radio | Medium | **High**: both off-grid LoRa |
| Audience | Low–medium | **Medium**: communities preparing for outages overlap with disaster response |
| Platform | Low | Low–medium: standalone Linux later, against their Docker and OpenWrt |

### 5.3 Risks

| ID | Risk | Severity |
|---|---|---|
| N-1 | Confusion and misdirected support, increased by app-store visibility from v0.3.0 | High |
| N-2 | Their organisation, repository name and mobile app already own search results for the name | Medium |
| N-3 | They hold earlier unregistered use; a later registration by them, or a passing-off claim, could force a rename after publication **[Assumption]** | Medium–high |
| N-4 | Safety: in an emergency, someone may install the wrong tool, or blame one project for the other's failure | Medium |
| N-5 | Permanence: slug, image name and `/data` location are fixed by the first published image (v0.3.0) | High |
| N-6 | Cost of renaming rises sharply after v0.3.0; before it, the only installations are the maintainer's local prototype, whose `/data` would need a one-off migration under a new slug (principle 8) | — |

### 5.4 Alternatives

| Option | Description | Effect on risk | Cost |
|---|---|---|---|
| A | Keep "MeshBeacon for Home Assistant" with ADR 0003's conditions (status quo) | N-1 to N-5 remain | None now; highest later |
| B | Keep MeshBeacon for the Home Assistant app; give the community network its own name | Partial; two names to explain | Low |
| C | Rename before v0.3.0 | Removes N-1 to N-5 if the new name is clear | Low now (documentation, slug, package name, one prototype migration) |

First-pass screening of possible names for option C (GitHub repository search and a general web
search only; **not** trademark clearance):

| Candidate | Screening result |
|---|---|
| Commonwave | Two unrelated, empty GitHub repositories; no web results found |
| Fieldlantern / Lanternmesh | No GitHub repositories; but "Lantern" is an established censorship-circumvention brand, a risk in the same privacy space |
| HearthMesh | **Rejected:** an existing project replicates verified public knowledge across resilient nodes, a direct overlap |
| Hearthnet, Kinmesh, Waymesh | Existing repositories with the name; not examined further |

Whatever the name, avoid upstream or ecosystem marks (Reticulum, LXMF, Nomad Network, Sideband,
Meshtastic, MeshCore) that could imply endorsement.

**[Recommendation]** Decide Q-50 before any v0.3.0 publication. If option A is kept, complete the
courtesy contact (RG-9) and register searches (RG-8) first, and rewrite the vision's pitch so that it
does not echo theirs. On current evidence, option C costs least now and removes most of the risk.
Any candidate needs register searches (UK IPO, EUIPO, WIPO, USPTO, MyIPO) and domain checks
before adoption.

## 6. Availability and collision assessment: "Commonwave" (19 November 2026)

Requested by the maintainer, who favours renaming before the first published release. **Nothing
has been renamed.** This is a screening, **not trademark clearance or legal advice**.

### 6.1 Method and limits

| Source | Method | Result obtained? |
|---|---|---|
| GitHub | Repository and user search (API); account pages (web) | Yes |
| PyPI, npm, crates.io, RubyGems, NuGet, Maven Central, Go module proxy, Docker Hub | Public registry APIs | Yes |
| F-Droid | Public API | **No** — host not reachable from this environment |
| Domains (`.com`, `.net`, `.org`, `.io`, `.app`, `.dev`, `.uk`, `.org.uk`, `.eu`, `.network`) | RDAP | **No** — RDAP hosts not reachable from this environment; web search only |
| UK IPO, EUIPO (TMview), WIPO Global Brand Database, USPTO, MyIPO | Official search | **No** — not reachable; one USPTO record found indirectly through a web search of a third-party mirror |
| General web | Search engines | Yes |

The official register searches therefore remain open (release gate RG-8) and must be run by the
maintainer for Commonwave or whichever name is chosen.

### 6.2 Findings

| Area | Finding | Label |
|---|---|---|
| GitHub account `commonwave` | Does not exist (404) | [Verified] |
| GitHub, similar accounts | Organisation `CommonWave-Studios` and user `CommonWaveStudios`: no public repositories, no description | [Verified] |
| GitHub repositories | Two unrelated repositories named `commonwave` (no description; last pushed May and September 2026) | [Verified] |
| Package registries | `commonwave` is unused on PyPI, npm, crates.io, RubyGems, NuGet, Maven Central and the Go proxy; no PyPI project contains the string; Docker Hub has no `commonwave` user or organisation | [Verified] |
| `commonwave.net` | Used by **Common Wave Hi-Fi**, a Los Angeles hi-fi and record shop (domain registered 2017 per a WHOIS mirror) | [Verified] use; [Assumption] registration date |
| `commonwave.com`, `.org`, `.io` and others | No site found by web search; registration status unknown | [Open] |
| USPTO | **COMMON WAVE HI FI**, a design (logo) mark, registration 6368621, registered 1 June 2021, Class 35 (retail/advertising services), owner Common Wave Hi-Fi — as reported by a third-party mirror, not read from the USPTO | [Assumption] until checked at the USPTO |
| Other registers | Not searched | [Open] |
| Confusable names | **Commonware** (commonware.xyz): infrastructure "enabling secure peer communication, data persistence"; one letter from Commonwave, in a related technical space. **Community Waves** (communitywaves.org): an ethical social platform for community changemakers run by Transition Network | [Verified] existence from web search |
| Mesh / radio ecosystems | No Reticulum, Meshtastic, MeshCore or amateur-radio project named Commonwave found | [Verified] for the sources above |

### 6.3 Assessment

| Risk | Rating | Reason |
|---|---|---|
| Collision with an existing mesh or off-grid project | **Low** | None found |
| Registered-mark conflict | Low–medium [Assumption] | The one known mark is a logo for retail services in a different field (audio retail), but it is a registered mark containing both words, and audio equipment is adjacent to radio |
| Confusion with Commonware | Medium | One letter apart, both about secure peer communication |
| Confusion with Community Waves | Low–medium | Similar words and a community audience; different product type |
| Domain availability | Unknown | `.net` is taken; others unverified |
| Search visibility | Medium | The hi-fi shop and its social accounts own current results |

**Verdict:** **Commonwave is usable but not cleared.** It removes the MeshBeacon collision
(§1, §5), which was the main problem. It brings milder risks: the Commonware look-alike, a
registered US design mark and an occupied `.net`. Adopt it only after the official register
searches (RG-8) and a domain check, both by the maintainer.

### 6.4 Alternatives screened

Same limits as §6.1 (GitHub, registries, web search; no registers, no RDAP).

| Candidate | GitHub | Registries | Web | Assessment |
|---|---|---|---|---|
| **Lanternpost** | No repositories; one user account | Free on PyPI, npm, Docker Hub | Nothing found | Clearest result of the screen, but "Lantern" is an established privacy/anti-censorship brand (§5.4) |
| **Fieldpost** | Two repositories, including a 2026 "FieldPost Everywhere" UX project; user `fieldpost` taken | Free | A construction job-site SaaS listing | Usable outside that field; weaker fit for a community network |
| Hearthwave | `Hearthwave`: a 2026 GMRS radio "family hub for home server" | Free | — | **Rejected:** radio and household overlap |
| HearthMesh | Existing resilient-knowledge project | — | — | **Rejected** (§5) |
| Commonlight | 43 repositories, 6 accounts | — | Close to the education brand CommonLit | **Rejected:** crowded |
| Wayfold, Tidepost | 15 and 5 repositories | Free | — | Crowded; not pursued |

**[Recommendation]** Carry **Commonwave** and **Lanternpost** to official register searches (UK IPO,
EUIPO, WIPO, USPTO; MyIPO if still wanted) and domain checks. Choose Commonwave if the registers
are clear, because it fits the community direction. Whatever is chosen also needs:

- new values in `project.yaml` (M1 keeps every project identifier there, and
  `tests/unit/test_project_identifiers.py` lists each file that must follow), including the app
  slug, which moves the app's data folder and changes the integration's domain. The integration's
  history survives that change, because the stable node key (ADR 0015 decision 5) is independent of
  the slug;
- a one-off data migration for the maintainer's local prototype, preserving the identity
  (ADR 0018);
- an updated ADR 0003.
