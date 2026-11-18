# Phase 0 feasibility study

Status: **Draft for review** · Research date: 18 November 2026

This document records the Phase 0 technical research for MeshBeacon. It is the evidence base for
[ADR 0001](../adr/0001-networking-foundation.md), the [architecture](../architecture.md), the
[roadmap](../roadmap.md) and the [threat model](../security/threat-model.md). Licensing is covered
separately in [licensing.md](licensing.md).

## How to read this document

Every substantive statement is labelled:

| Label | Meaning |
|---|---|
| **[Verified]** | Checked directly against upstream source code, an upstream document at the recorded revision, or by running the software in an isolated test. The source is cited. |
| **[Assumption]** | Believed to be true but not verified in Phase 0. Must be verified before it is relied on. |
| **[Recommendation]** | Our proposed course of action, with reasoning. Open to challenge. |
| **[Open]** | An unresolved question that needs a decision or further investigation. Numbered `Q-n` and collected in [§14](#14-unresolved-questions). |

Line numbers refer to the file at the recorded revision and will drift as upstream changes.

### Provenance of this research

This research was carried out by an AI coding assistant (Claude, by Anthropic) working in a
sandboxed cloud environment on behalf of, and at the direction of, the repository owner. Upstream
repositories were cloned and read locally, and RNS was installed into an isolated virtual
environment for the measurements in §9. The assistant could not reach `reticulum.network`,
`ratspeak.org` or `developers.home-assistant.io` directly (network policy); the Reticulum manual and
the Home Assistant developer documentation were instead read from their source repositories at the
revisions recorded below. **All findings require review by a human maintainer before they are
relied on.** See §10.1 for why provenance matters particularly in the Reticulum ecosystem.

## 0. Final decisions before Phase 1 (18 November 2026)

| Decision | Value |
|---|---|
| Name / slug / tagline | MeshBeacon · `meshbeacon` · "Decentralised connectivity for your home." |
| Licence | Apache-2.0 for original code and documentation |
| AI training | Disabled on the maintainer's ChatGPT and Claude accounts (Q-15) |
| Reference hardware | Raspberry Pi 4B, 8 GB, `aarch64`, HA OS 18.5 |
| N2K collaboration | Deferred until a working prototype exists (Q-2) |
| Release gates | Trademark checks, external project contact, public peer verification and distribution compliance gate **public release**, not local development (roadmap tier B) |
| Recovery | Bounded internal recovery that cannot loop with the Supervisor watchdog (architecture §4.2, §4.5; ADR 0005) |
| Logging | No identity or destination hashes in logs, including during identity replacement |

## 0.1 Review amendments (18 November 2026)

Following independent review, the following were added or changed. The original Phase 0 text
below is retained, with corrections where noted.

| Topic | Where |
|---|---|
| Licence decided (Apache-2.0); dependency compatibility; AI-training analysis; publication obligations | [licensing.md](licensing.md), [ADR 0002](../adr/0002-licence.md) |
| Deeper investigation of the existing MeshBeacon organisation; trademark checks; name retained with conditions | [naming.md](naming.md), [ADR 0003](../adr/0003-name.md) |
| Ease of use as a core principle; five-minute first run | [first-run UX](../ux/first-run.md) |
| Optional public peer presets (Ratspeak Ruby, Emerald, Diamond as candidates) | [public-peers.md](public-peers.md), [ADR 0004](../adr/0004-public-peer-presets.md) |
| Non-root service user, configuration-injection prevention, resource guards, health vs connectivity, crash-safe identity, watchdog behaviour | [architecture §4](../architecture.md#4-core-internals) |
| New verified findings: RNS silently replaces a corrupt identity (§7.1); naive config templating is injectable (architecture §4.1); Supervisor watchdog semantics (architecture §4.5); `rns` wheel ships no licence file (licensing §3.1) | as noted |
| v0.1.0 scope narrowed | [roadmap](../roadmap.md) |
| Reference environment confirmed (Q-5 resolved); compatibility, soak, outage, power and backup test plans | [reference environment](../testing/reference-environment.md), [testing strategy §6](../testing/strategy.md#6-reference-environment-testing-before-each-release) |
| Security rating 8 treated as a target, not proof | [threat model](../security/threat-model.md) |

## 1. Upstream revisions reviewed

| Project | Source | Version / revision | Date | Licence (verified) |
|---|---|---|---|---|
| Reticulum (RNS) | PyPI `rns` | **1.6.0** (latest release) | 2026-11-07 | Reticulum License |
| Reticulum (RNS) | github.com/markqvist/Reticulum (public mirror) | `4a058544a5205835f93aa6178b23b7eadf5d6b1f` (`_version.py` = 1.6.1, unreleased) | 2026-11-18 | Reticulum License |
| Reticulum manual | `docs/source/*.rst` in the same commit | as above | 2026-11-18 | Reticulum License |
| LXMF | PyPI `lxmf` | **1.3.0** (requires `rns>=1.6.0`) | 2026-11-07 | Reticulum License |
| LXMF | github.com/markqvist/LXMF | `7dfc8353541f46e1c5aceab4849136dc28bb7855` | 2026-11-17 | Reticulum License |
| Rathole | github.com/ratspeak/rathole | `917b2ac91c39e46a88215b88d6d6a5854b31f401` (`pyproject` 1.0.0) | 2026-11-02 | GPL-3.0-or-later |
| rsReticulum (Ratspeak) | github.com/ratspeak/rsReticulum | `e8a21ce00c96876694916285b49b6cba9a5030f7` | 2026-11-17 | Reticulum License (derivative, "Additions … Ratspeak LLC") |
| Sideband | github.com/markqvist/Sideband | tag `2.2.0` (`ef572b58e88ff4e4326d51778336922a53b2a03f`) | 2026-10-01 | CC BY-NC-SA 4.0 |
| RNode firmware | github.com/markqvist/RNode_Firmware | `56775c51b60a6190242e324c210997dcc7637e53` (1.86+4) | 2026-09-27 | GPL-3.0 |
| HA developer docs | github.com/home-assistant/developers.home-assistant | `50b518898989b67bb76b69827f227aa6f0acd32a` | 2026-10-16 | (docs) |
| HA Supervisor | github.com/home-assistant/supervisor | `e610ca810eab5f7444dfb7f74a3b7c869685c797` | 2026-11-16 | Apache-2.0 |
| HA base images | github.com/home-assistant/docker-base | `7d9ba088153e553eb364a586bd9c6f814e19166c` | 2026-11-06 | Apache-2.0 |
| HA builder actions | github.com/home-assistant/builder | `5c723bda7361c2de085c639324d900bcade86ca8` | 2026-11-16 | Apache-2.0 |

**[Verified]** The GitHub Reticulum repository is a *public mirror only*. `MIRROR.md` at the
reviewed commit states: "All potential future development is happening elsewhere", and that there
will be "no support, no responses to issues, no discussions, and no community management in this or
any other public venue". Releases continue to be published to PyPI (1.6.0 on 2026-11-07).

## 2. Reticulum versus Rathole (research item 1)

### 2.1 What Rathole is

**[Verified]** Rathole describes itself in its README as "a proof of concept" and on GitHub as a
"Prototype Reticulum gateway and transport-node management tools". It is ~13,000 lines of Python
(`src/rathole/**/*.py`), six commits in total (2026-03-20 to 2026-11-02), a single author account,
and has **no test suite** in the repository.

**[Verified]** Rathole integrates with RNS by monkeypatching private internals
(`src/rathole/hook.py`, `src/rathole/daemon.py`):

- It replaces `RNS.Transport.inbound()` and `RNS.Transport.path_request_handler()` with wrappers.
  Its own docstring warns: "This hooks into RNS internals. If Reticulum's Transport API changes,
  this module may need updating. Pin your RNS version."
- It re-implements packet header parsing (`_extract_context_from_raw`) instead of using RNS's own
  parser, and skips IFAC-authenticated packets because it cannot parse them.
- It writes name-mangled private attributes: `RNS.Reticulum._Reticulum__transport_enabled = True`
  (daemon.py ~L404) and `RNS.Reticulum._Reticulum__instance = None` (daemon.py ~L300).
- Its dependency declaration is `rns>=0.7.0`; its README states this "is not a tested compatibility
  range".
- Its README states it "attempts to enable transport at startup, including in its **client** mode",
  that setup "can change [the existing Reticulum configuration's] interfaces and transport setting",
  and that its default registry discovery is an HTTPS request to `registry.ratspeak.org`, which
  "exposes [your source IP] to the registry endpoint". Registry publishing announces the node's I2P
  address, name, version and mode.

### 2.2 What RNS now provides natively

**[Verified]** RNS 1.6.0 (Changelog.md, `RNS/Reticulum.py` `__apply_config`) added, in core:

- a `[filter]` configuration section (`required_only`, `ignored_types`, `allowed_types`,
  `hop_limiter`);
- network stamps (proof-of-work anti-spam) for identities, announces, path requests and link
  requests, with a phased roll-out: 1.6.0 verifies, 1.6.1 emits by default, **1.6.2 enforces by
  default** ("Any old transport nodes that have not updated to `1.6.x` will not be able to
  communicate with stamp-enforcing nodes");
- ingress and burst control, blackhole management (`blackhole_identity()`, `blackhole_sources`),
  and fast-flap blocking for `BackboneInterface` listeners (manual: `protecting.rst`,
  `interfaces.rst` "Automated Blocking").

These cover most of the *protective* purpose Rathole was written for, without monkeypatching.

### 2.3 Assessment

| Criterion | Build directly on RNS | Depend on Rathole |
|---|---|---|
| Maturity | Reference implementation, >10 years, frequent releases | Self-described proof of concept, 6 commits, no tests |
| Integration method | Public API, config file, RPC | Monkeypatches private internals |
| Upgrade safety | Normal semver-ish releases | Breaks silently on RNS internal changes |
| Privacy defaults | No discovery/autoconnect by default (verified, §8) | Registry over HTTPS; enables transport in client mode |
| Licence fit | Reticulum License (permissive + conditions) | GPL-3.0 combined with Reticulum License — see licensing §3.3 |
| Protective features | Native filters, stamps, blackholes (1.6.x) | Additional heuristic filters, reputation, TUI |

**[Recommendation]** The preliminary preference **is upheld**: build directly on RNS and do not
depend on, vendor or import Rathole. This is recorded in [ADR 0001](../adr/0001-networking-foundation.md).

### 2.4 Challenging the recommendation

In fairness to Rathole, and to test the decision:

- **Rathole solves a real problem.** A public gateway attracts announce floods and abusive peers.
  If MeshBeacon later offers a public gateway (v0.4), it will need protections. *Response:* RNS 1.6
  now has native equivalents; MeshBeacon should use those, and file upstream-style feature requests
  (noting the mirror accepts none) rather than patch internals.
- **Rathole's operator experience (TUI, metrics) is useful.** *Response:* `rnstatus -j` and the RNS
  RPC already expose structured metrics (verified, §13); MeshBeacon can present these in Home
  Assistant without patching.
- **Ideas, not code, may be borrowed.** Rathole's I2P gateway workflow and alert concepts are
  worth studying as design input. Code must not be copied (GPL-3.0; see licensing).
- **The strongest counter-argument against our own choice** is that RNS upstream is now a
  low-interaction mirror with a single maintainer who has publicly stepped back (§1). Building
  "directly on RNS" still means depending on a single-maintainer project. Rathole does not reduce
  that risk — it *increases* it, because it depends on RNS internals as well as on RNS. Mitigations
  are listed in §15 (risk R-1).

## 3. Upstream licences and distribution (research item 2)

Summarised here; full analysis in [licensing.md](licensing.md).

- **[Verified]** RNS and LXMF use the **Reticulum License**: MIT-style grant plus two field-of-use
  conditions (no use in systems designed to purposefully harm humans; no use in creating AI/ML
  training datasets) and an attribution condition.
- **[Verified]** Sideband is CC BY-NC-SA 4.0 — its code must not be reused in MeshBeacon.
- **[Verified]** Rathole and RNode firmware are GPL-3.0.
- **[Recommendation]** MeshBeacon depends on RNS/LXMF as unmodified PyPI packages, ships their
  licence text in the container image, and copies no upstream source into this repository.
- **[Decision]** (review amendments) MeshBeacon's own code is Apache-2.0 — see [ADR 0002](../adr/0002-licence.md).

## 4. Competing projects and naming (research item 3)

Searched GitHub (repository search, 18 November 2026). Revisions are recorded where cloned.

### 4.1 Direct or near competitors

| Project | What it is | Notes (verified from its repository) |
|---|---|---|
| **N2K RNS Gateway** — `netfreak2k/home-assistant-reticulum` (`090b6a1`, MIT) | HA app running RNS + LXMF messenger with ingress UI | Public beta 1.22.0-beta1. `config.yaml` sets `host_network: true`, `uart: true`, `hassio_api: true`, `homeassistant_api: true`, maps `homeassistant_config` **read-write**, and defaults `internet_bootstrap: true`. UI text partly German. Closest competitor. |
| **Rover** — `BotoVed/haos-rover` (`b08a7cf`, GPL-3.0) | HA custom integration (HACS) for smart-home control over Reticulum/LXMF | README in Russian. Runs inside HA Core as a custom component. Overlaps with our v0.6. |
| **MeshMonitor for HA** — `X-Faktor-Technologies/home-assistant-meshmonitor` (`e9f1335`, BSD-3-Clause) | HA integration for an external MeshMonitor server covering Meshtastic, MeshCore *and* Reticulum | Overlaps with our v0.2 visibility goals; depends on a separate server. |
| **NOEMA RNSGate** — `e2ret/NOEMA-RNSGate-Lite` (MIT) / `-FULL` | Reticulum gateway combining LoRa, LXMF and (per description) HA | Not cloned; description only. |
| **Meshtastic HA integration** — `meshtastic/home-assistant` (GPL-3.0, 443★) | Different protocol (Meshtastic) | Shows demand for mesh-in-HA; not Reticulum-compatible. |

**[Recommendation]** MeshBeacon's differentiation should be its **security posture** (no host
network, no HA config write access, no Supervisor API, no automatic internet bootstrap by default),
**separation of core and HA layers**, and **testability** — not feature count. Before Phase 1 the
maintainer should consider contacting the N2K author to explore collaboration, since duplicated
effort in a small ecosystem has a real cost. **[Open] Q-2.**

### 4.2 Naming conflicts

**[Verified]** The name "MeshBeacon" is already in use, in the same domain:

- **GitHub organisation `MeshBeacon`** — "MeshBeacon Ops: Offline-first incident operations for
  mesh-connected response teams" (`MeshBeacon/meshbeacon`, Apache-2.0, Laravel/PHP, `ce98774`,
  active Oct 2026), plus `ots-meshbeacon-plugin` (OpenTAKServer, GPL-3.0) and
  `openwrt-meshbeacon-package` (AGPL-3.0). This is the most significant conflict: same name, same
  "mesh" problem space, with an established organisation and logo.
- `salmancuso/MeshBeacon` — "MeshCore Broadcast System" for amateur-radio LoRa meshes (May 2026).
- `shimco/meshbeacon` — unrelated smart-TV discovery beacon.

**[Assumption]** No trademark search (UKIPO, EUIPO, USPTO) has been done.

**[Recommendation]** Treat the name as **at risk**. Decide before the first public release, while
renaming is cheap. Options: keep the name with clear disambiguation; or rename (for example a name
that signals Home Assistant + Reticulum). *(Review amendments: investigated further in
[naming.md](naming.md); name retained with conditions — [ADR 0003](../adr/0003-name.md).)*

## 5. Home Assistant app packaging (research item 4)

**[Verified]** Home Assistant has renamed add-ons to **apps** ("Apps (formerly known as add-ons)",
`docs/apps.md`). Behaviour and file layout are unchanged; some identifiers changed, e.g. the map
type is documented as `app_config` (the N2K competitor still uses the older `addon_config`).
**[Open] Q-4**: confirm which identifiers the Supervisor on the target device accepts.

Verified from `docs/apps/configuration.md`, `docs/apps/security.md`, `docs/apps/publishing.md` and
Supervisor `supervisor/apps/utils.py`:

- An app is a folder with `config.yaml`, `Dockerfile`, `DOCS.md`, `README.md`, `CHANGELOG.md`,
  `icon.png`, `logo.png`, `translations/en.yaml`, and optionally `apparmor.txt`.
- **`build.yaml` is no longer used.** Since Supervisor 2026.04.0 `BUILD_FROM` is not supplied; the
  Dockerfile must `FROM` an explicit (preferably pinned) base image.
- `arch` accepts only **`aarch64` and `amd64`**.
- `/data` is always mapped and writable; `/data/options.json` holds user options.
- Relevant security options and their defaults: `host_network: false`, `hassio_api: false`,
  `homeassistant_api: false`, `auth_api: false`, `docker_api: false`, `full_access: false`,
  `apparmor: true`, `privileged:` (list of capabilities), `uart`/`usb`/`devices` (hardware).
- Lifecycle options: `startup`, `boot`, `watchdog` (HTTP or `tcp://` health URL), `timeout`,
  `init`, `stage` (`stable`/`experimental`/`deprecated`), `ulimits`, `tmpfs`.
- Backup options: `backup: hot|cold`, `backup_pre`, `backup_post`, `backup_exclude` (globs).
- **Security rating (Supervisor `rating_security`)**, clamped to 1–8, starts at 5: +1 custom AppArmor profile;
  +2 if ingress, *or* if no host network and no published ports; +1 signed image; −1 for host
  network; −1 for sensitive capabilities (`NET_ADMIN`, `NET_RAW`, `SYS_ADMIN`, …); −1/−2 for
  `manager`/`admin` Supervisor roles.
- Published images should be multi-arch, built and **Cosign-signed** with the
  `home-assistant/builder` reusable actions (`prepare-multi-arch-matrix`, `build-image`,
  `publish-multi-arch-manifest`, `cosign-verify`).
- **[Verified]** The Supervisor passes no memory or CPU limits for apps
  (`supervisor/docker/app.py` sets only `cpu_rt_runtime`; there is no `mem_limit`). Only `ulimits`
  are configurable. Resource protection must therefore be built into MeshBeacon itself (§9.4).

**[Verified]** The official HA Python base images are Alpine-based (`docker-base/python/3.13`
defaults to `ghcr.io/home-assistant/base:3.23` with CPython 3.13.18, built from signature-verified
sources), with 3.14 and 3.15 variants available.

**[Recommendation]** v0.1.0 config posture:

```yaml
# Illustrative only — not implementation.
arch: [aarch64, amd64]
startup: services            # start before HA Core so integrations find it
boot: auto
host_network: false
hassio_api: false
homeassistant_api: false
apparmor: true               # plus a custom profile (apparmor.txt)
stage: experimental
backup: hot
ports: {}                    # no published ports by default
watchdog: "tcp://[HOST]:[PORT:…]"   # internal health endpoint, to be designed
```

This should reach the maximum Supervisor security rating of **8**: 5 +1 custom AppArmor profile
+2 no ports/host network = 8, and the function clamps to `max(min(8, rating), 1)` (verified), so
signing adds no further points but is still required for supply-chain integrity. Any later opt-in
(device access, a published port) lowers it. **[Assumption]** — confirm on a real Supervisor. The
rating is a **target, not proof of security** (threat model, preamble).

## 6. ARM64 and AMD64 compatibility (research item 5)

- **[Verified]** `rns` 1.6.0 and `lxmf` 1.3.0 are published as pure-Python `py3-none-any` wheels;
  `rns` requires `cryptography>=3.4.7` and `pyserial>=3.5`; `requires_python >=3.7`.
- **[Verified]** `cryptography` 50.0.2 publishes `musllinux_1_2_aarch64` wheels (downloaded during
  research), so an Alpine aarch64 image needs no Rust toolchain at build time.
- **[Verified]** RNS falls back to internal pure-Python primitives if `cryptography` is missing
  (`RNS/Cryptography/Provider.py`), but this would be slower. **[Recommendation]** Require
  `cryptography` explicitly; fail loudly rather than fall back silently.
- **[Verified]** The HA builder actions build `aarch64` natively or under QEMU; Docker's
  `linux/arm64` corresponds to HA's `aarch64`.
- **[Assumption]** No ARM-specific behaviour in RNS for TCP-only use. RNode/serial (v0.5) adds
  USB-serial driver questions on HA OS that are not covered here.
- **[Verified — resolved Q-5]** The maintainer has confirmed the reference device: Raspberry Pi 4B,
  machine type `rpi4-64`, **`aarch64`**, **Home Assistant OS 18.5**, Core 2026.11.2, Supervisor
  2026.11.0 (healthy, supported). This is a 64-bit HA OS installation on one of the two
  architectures the Supervisor accepts, so no 32-bit build is needed. Details, co-installed apps
  and open items: [reference environment](../testing/reference-environment.md).
- **[Verified]** Supervisor 2026.11.0 has the same watchdog interval and security-rating logic as
  the commit reviewed in §1 (reference environment §1).

## 7. Persistent identity, backups and recovery (research item 6)

### 7.1 What RNS stores

**[Verified]** (`RNS/Reticulum.py` ~L257–L360, `RNS/Transport.py` ~L424–L445):

- Config directory: `--config` argument, else `/etc/reticulum`, `~/.config/reticulum`, or
  `~/.reticulum`. Storage lives in `<configdir>/storage/`.
- **Transport identity**: `<configdir>/storage/transport_identity`, a raw 64-byte private key
  (`Identity.to_file()` writes `get_private_key()` verbatim — no encryption, no header).
- If transport is *disabled* and `static_transport_identity` is not set, the network-facing
  transport identity is **ephemeral** (regenerated each start); the stored one is kept as the
  internal identity. Enabling transport makes the stored identity the public one.
- The **shared-instance RPC key** defaults to `full_hash(transport_identity private key)` unless
  `rpc_key` is configured. Anyone holding the identity file can therefore authenticate to the RPC.
- 1.6.0 uses SQLite by default (`known_destinations.db` with WAL files), and auto-migrates legacy
  file storage on first start.
- Other storage: `cache/`, `resources/`, `blackhole/`, `identities/`, and (LXMF)
  `<storage>/lxmf/state.db` and `ratchets/`.

**[Verified by test]** Started under the default umask, RNS 1.6.0 created `transport_identity`
with mode **0644** (world-readable) and the storage directories 0755.

**[Verified by test, review amendments]** RNS **silently replaces a corrupt identity**. With a
10-byte random `transport_identity`, `rnsd` 1.6.0 logged "Failed to load identity key …" and "No
valid Transport Identity in storage, creating…", and overwrote the file with a new 64-byte key.
`Identity.to_file()` writes in place (no temporary file, `fsync` or rename), so a power cut during
the first write can produce exactly this state. Design response: architecture §4.6.

### 7.2 Recommendations

- **[Recommendation]** Put the RNS config directory under `/data/reticulum` (always mapped and
  persistent). Run the service with `umask 077` and verify/repair permissions (`0600` files,
  `0700` directories) at every start, *before* RNS starts.
- **[Recommendation]** Set a distinct `instance_name` and an explicit, randomly generated
  `rpc_key` so that RPC access is not derived from the identity key.
  **[Verified]** `rpc_key` is read from `[reticulum]` as a hex string (`bytes.fromhex`); an
  invalid value logs an error and **silently falls back to the identity-derived key**
  (`RNS/Reticulum.py` ~L616–L622). MeshBeacon must therefore validate the generated value itself,
  and the generated RNS `config` file (which then contains a secret) must be 0600.
  **[Open] Q-6** whether the RPC client side (`rnstatus` etc.) picks up `rpc_key` from the same
  config in all code paths.
- **[Recommendation]** Include the identity in HA backups (hot backup). Exclude regenerable data
  (`cache/`, `resources/`) via `backup_exclude`. Use `backup_pre` to checkpoint the SQLite WAL so a
  hot backup captures a consistent database. **[Open] Q-7** whether a WAL checkpoint while RNS is
  running is safe, or whether `backup: cold` is required for correctness.
- **[Recommendation]** HA backups can be encrypted by HA, but MeshBeacon must document that an
  unencrypted backup contains the private key. Offer an explicit, opt-in identity export (for
  migration) and never print key material.
- **[Recommendation]** Recovery: on corrupt or missing identity, **do not silently generate a new
  one** if one previously existed (that would change the node's address and break contacts);
  stop with a clear error unless the user explicitly opts to regenerate. A first-ever start may
  generate one. Because RNS itself would regenerate (above), MeshBeacon must validate the identity
  *before* starting RNS — see architecture §4.6.

## 8. CGNAT and connectivity options (research item 7)

The target uplink is 5G broadband, likely behind carrier-grade NAT (CGNAT; unconfirmed — Q-32):
**outbound connections work; unsolicited inbound connections do not.** On the reference device the
default network interface is **Wi-Fi**, not Ethernet as originally assumed (Q-31); Wi-Fi drops are
treated as connectivity events, not failures.

| Option | Works behind CGNAT? | Privacy | Notes |
|---|---|---|---|
| `TCPClientInterface` / `BackboneInterface` to a chosen remote | **Yes** (outbound) | Remote sees your IP | Default for v0.1. User must choose a remote; we ship no default (see below). |
| `TCPServerInterface` / `BackboneInterface` listener | No (without port forwarding) | Exposes a port | Off by default; not useful behind CGNAT. |
| Over Tailscale (tailnet IPs) | **Yes** | Only tailnet members can reach it | Good for linking the user's own nodes. MeshBeacon would just listen on / connect to a tailnet address; no Tailscale integration needed. **[Assumption]** HA's Tailscale app exposes tailnet routing to other apps' bridged containers — needs testing (**Q-8**). |
| `I2PInterface` (`connectable = yes`) | **Yes** | Hides IP from Reticulum peers | Requires an I2P router with SAM (e.g. `i2pd`) — another process or container, extra RAM, slow first start (manual: `interfaces.rst` "I2P Interface"). v0.4 scope. |
| `AutoInterface` (LAN multicast) | LAN only | Visible to LAN | Enabled in RNS's *default* config (verified). Needs host networking for multicast — conflicts with our posture. Off for v0.1. |
| Yggdrasil | Yes (overlay) | Overlay peers see you | Supported by `BackboneInterface`; out of scope. |
| VPS relay | Yes | VPS operator sees traffic metadata | Contradicts "no mandatory third-party dependencies" if required; acceptable as user choice. |

**[Verified]** RNS defaults (generated default config, `RNS/Reticulum.py` ~L2580–L2710 and
~L285–L300): `enable_transport = False`, `share_instance = Yes`, `discover_interfaces` off,
`autoconnect_discovered_interfaces` off, interface `discoverable` off, and **one `AutoInterface`
enabled**.

**[Verified]** Interface discovery, when enabled, can publish `reachable_on` (public address),
`discovery_lxmf_address`, an operator name, and — via `location_cmd` — a location; `publish_ifac`
can publish an interface passphrase (manual: `interfaces.rst` §"Discoverable Interfaces").

**[Recommendation]** MeshBeacon generates its own RNS config from validated options rather than
using the RNS default. It **never** enables `AutoInterface`, `discoverable`, `discover_interfaces`,
`autoconnect_discovered_interfaces`, `publish_ifac` or `location_cmd` unless the user explicitly
opts in (and v0.1 exposes none of them).

**[Recommendation]** Ship **no default remote**. *(Review amendments: optional, verified presets
are now planned — see [public-peers.md](public-peers.md) and ADR 0004.)* The manual uses
`amsterdam.connect.reticulum.network` in examples and Rathole uses `rns.ratspeak.org:4242`, but
connecting by default would leak the user's IP to a third party and violate "no automatic
connection to untrusted interfaces". Documentation may list well-known entry points with a privacy
note. **[Open] Q-9** — the first-run experience without a default remote needs UX design.

## 9. Resource consumption and network impact (research item 8)

### 9.1 Measured (isolated test)

**[Verified by test]** Two `rnsd` 1.6.0 processes (CPython 3.13.18, x86-64, `cryptography`
50.0.2), one transport-enabled TCP server and one TCP client on loopback, no other traffic:

| Instance | VmRSS (idle, ~10 s after start) | Threads |
|---|---|---|
| Transport node (TCP server) | ~55 MB | 12 |
| Client (TCP client) | ~54 MB | 11 |

`rnstatus -j` also reports an `rss` field, so memory can be monitored without extra tooling.

**[Assumption]** On aarch64 the figure will be similar. Memory will grow with path-table and
announce-table size on a transport node connected to a busy network; the 1.6.0 changelog claims
~50% memory reduction for long-running transport nodes and introduces path-table culling. Not
measured here. **[Open] Q-10**: soak-test on the reference Pi 4B — 72 hours with transport off and at least
7 days with transport on ([testing strategy §6.3](../testing/strategy.md#63-soak-tests)).

### 9.2 CPU

**[Verified]** RNS 1.6.x stamps (proof-of-work) cost CPU: the changelog warns "Expect some CPU
usage when an unstamped destination has its stamp generated for the first time". **[Assumption]**
This is a one-off per destination, but on a Pi it could take noticeable time; it must not block
HA. Measure in Phase 1.

### 9.3 Network impact

- **[Verified]** A *transport* node routes traffic for others, passes announces and serves path
  requests (default config comment). On a busy network this consumes bandwidth on a 5G plan.
- **[Recommendation]** Transport mode is **off by default**, opt-in, with documentation of the
  bandwidth implications. Use per-interface `announce_rate_*` / ingress control and the `[filter]`
  section when transport is enabled. Expose RX/TX byte counters (v0.2) so users can see the cost.
- **[Recommendation]** Be a good network citizen: no custom announce behaviour, conservative
  announce intervals, no bulk link creation, no scraping. This is also an explicit community
  expectation (§10.1).

### 9.4 Protecting the host

Because the Supervisor sets no memory limits (§5):

- **[Recommendation]** A MeshBeacon supervisor process monitors the RNS child's RSS and restarts it
  (with back-off) above a configurable ceiling (initial proposal: 256 MB).
- **[Recommendation]** Use `ulimits` (e.g. `nofile`) sensibly; bound log volume; use SQLite on
  `/data` (SSD), never on tmpfs.

## 10. Security and privacy risks (research item 9)

Detailed in the [threat model](../security/threat-model.md). Key findings verified in Phase 0:

1. **[Verified]** Private key stored unencrypted, 0644 under default umask (§7.1).
2. **[Verified]** RPC authentication key derived from the identity private key by default (§7.1).
3. **[Verified]** On Linux, the shared instance and its RPC listen on **abstract Unix sockets**
   (`\0rns/<instance_name>` and `\0rns/<instance_name>/rpc`; `RNS/Reticulum.py` ~L392,
   `RNS/vendor/platformutils.py` `use_af_unix()`), observed as `@rns/mbtest_a`, `@rns/mbtest_a/rpc`
   in `/proc/net/unix` during testing. Abstract sockets are scoped to the **network namespace**,
   not the filesystem. With `host_network: true`, every process in the host network namespace —
   including other host-network apps — could connect to the shared instance. The data socket has
   no authentication of its own. **This is a strong, concrete reason to keep `host_network:
   false`.**
4. **[Verified]** RNS defaults include LAN multicast discovery (`AutoInterface`) (§8).
5. **[Verified]** Interface discovery can publish address, contact and location data (§8).
6. **[Verified]** Competitor N2K maps the HA configuration directory read-write and enables
   Supervisor and Core APIs (§4.1) — shows the risk profile users may already accept; we should
   not.
7. **[Assumption]** RNS log output at default level 4 does not contain private keys. Grep of the
   source found no log statements printing `get_private_key()` output, but MeshBeacon must still
   filter its own logs and must never raise RNS log level above 4 in production by default.

### 10.1 Ecosystem trust and provenance

**[Verified]** The Reticulum repository at the reviewed commit contains a long document
(`AGENTS.md`, titled "Brandolini's Reference", also published as `docs/source/brandolinis.rst`) in
which the upstream author sets out, among other things:

- that machine *assistance* is acceptable but machine *substitution* is not; the test is whether a
  named human "can answer for" the work;
- that concealed AI provenance (for example tooling that strips AI attribution) is treated as a
  marker of untrustworthy projects;
- an evaluation framework for Reticulum projects (credit to the reference implementation, licence
  compliance, disclosed provenance, honest labelling as experimental, interop verified against
  current RNS on real media, readable code, network citizenship, "real builders ship, then talk");
- strong criticism of machine-generated "Reticulum implementations".

MeshBeacon is **not** a Reticulum implementation — it uses the reference implementation unchanged —
so most of that critique does not apply directly. But the ecosystem will judge MeshBeacon by those
standards, and this Phase 0 research was itself produced with an AI assistant.

**[Recommendation]**

- Disclose AI assistance openly and accurately (README, CONTRIBUTING, commit authorship). Do not
  remove or hide attribution.
- A named human maintainer must review and be able to answer for every merged change.
- Label the project **experimental** prominently until v1.0 (HA `stage: experimental`).
- Credit RNS and LXMF prominently; ship their licence notices.
- Avoid marketing-first behaviour: no benchmark claims, no "drop-in replacement" language.
- Never implement or "improve" protocol behaviour; never change behaviour on shared media.

**[Verified]** The Open Home Foundation (Home Assistant) AI policy (`docker-base/AI_POLICY.md`)
does **not allow autonomous agents to contribute** to OHF projects and requires a human who
understands any AI-assisted contribution. This matters if MeshBeacon ever contributes upstream to
Home Assistant repositories (for example a core integration).

## 11. Automated integration testing with isolated Reticulum networks (research item 10)

**[Verified by test]** Fully isolated Reticulum networks are straightforward:

- Each instance gets its own `--config` directory, a unique `instance_name` (which isolates the
  abstract sockets), and interfaces bound to `127.0.0.1` (or a private container network).
- With no `AutoInterface` and no external remotes, nothing leaves the test host.
- A TCP server/client pair connected within ~5 s (the client's first attempt raced the server and
  retried automatically — itself a useful recovery test).
- `rnstatus --config <dir> -j` returns machine-readable status (interfaces, byte counters, link
  counts, `rss`) suitable for assertions.
- Upstream's own tests use the same approach (`tests/rnsconfig/config`: unique `instance_name`,
  distinct ports, no interfaces).

**[Verified]** RNS uses a process-wide singleton (`RNS.Reticulum`), so multiple nodes in one test
require **multiple processes** (or containers), not multiple objects in one interpreter.

The full approach is in the [testing strategy](../testing/strategy.md).

## 12. Separation between core service and Home Assistant components (research item 11)

**[Verified]** Options for surfacing data in HA:

1. App writes states via `homeassistant_api` (`POST /api/states`) — entities are not persistent,
   have no unique IDs/devices, and require Core API permission. Not recommended.
2. MQTT discovery — needs an MQTT broker; optional dependency, extra moving part.
3. **A custom integration** (installable via HACS) that talks to the app over a small local API,
   discovered via the Supervisor discovery mechanism (`discovery:` in `config.yaml`), as done by
   first-party apps such as MQTT and Z-Wave JS. **[Assumption]** Supervisor discovery requires the
   app to have `hassio_api` access to *publish* a discovery message; verify the exact permission
   (**Q-11**). Manual configuration (host/port/token) is the fallback.
4. Running RNS inside HA Core as a custom component (the Rover approach) — couples RNS's singleton,
   threads and crash behaviour to HA Core. Not recommended.

**[Recommendation]** Option 3, with a strict split described in the
[architecture](../architecture.md): a HA-agnostic **core service** (Python package, runs anywhere,
standalone Docker in v1.0) and thin **HA adapters** (the app wrapper and, from v0.2, the
integration).

## 13. Reusable upstream utilities and APIs (research item 12)

**[Verified]** Available in `rns` 1.6.0 and `lxmf` 1.3.0 (no need to reimplement):

| Need | Reuse | Source |
|---|---|---|
| Run the stack | `rnsd` (`RNS/Utilities/rnsd.py`) or `RNS.Reticulum(configdir=…)` | Reticulum.py |
| Status / statistics | `RNS.Reticulum.get_interface_stats()`, `get_path_table()`, `get_rate_table()`, `get_link_count()`, `get_next_hop()`; CLI `rnstatus -j` | Reticulum.py ~L1707–L2193; rnstatus.py |
| Path management | `rnpath`, `drop_path()` | Utilities/rnpath.py |
| Reachability probe | `rnprobe` | Utilities/rnprobe.py |
| Identity tooling | `rnid` (generate, inspect, export) | Utilities/rnid.py |
| Abuse protection | `[filter]`, `[stamps]`, `blackhole_identity()`, `blackhole_sources` | Reticulum.py, protecting.rst |
| Interface access control | IFAC (`network_name`, `passphrase`) | interfaces.rst |
| Messaging | `LXMF.LXMRouter` (requires a storage path), `LXMessage` | LXMF/LXMRouter.py |
| Propagation node | `lxmd` with `[propagation] enable_node` | LXMF/Utilities/lxmd.py |
| RNode config | `rnodeconf` | Utilities/rnodeconf.py |

**[Recommendation]** v0.1 runs RNS **in a child process managed by the MeshBeacon core**, using
RNS's own config file format, and obtains status through RNS's public RPC/API rather than parsing
logs. Whether to launch `rnsd` itself or a thin Python entry point that instantiates
`RNS.Reticulum` is a Phase 1 detail (**Q-12**).

## 14. Unresolved questions

Status as of the review amendments (18 November 2026). Resolved items are kept for traceability.

| ID | Question | Status / owner |
|---|---|---|
| Q-1 | Licence for MeshBeacon's own code | **Resolved:** Apache-2.0 ([ADR 0002](../adr/0002-licence.md)) |
| Q-2 | Collaborate with N2K RNS Gateway rather than compete? | **Deferred** by the maintainer until a working MeshBeacon prototype exists |
| Q-3 | Keep the "MeshBeacon" name? | **Resolved, conditionally:** keep, with disambiguation and rename triggers ([ADR 0003](../adr/0003-name.md)) |
| Q-4 | Which Supervisor identifiers (`app_config` vs `addon_config`) apply on the target? | **Moot for v0.1:** the app maps no folders (`/data` is always mapped). Revisit if a mapping is ever added |
| Q-5 | Confirm target HA installation type and architecture | **Resolved:** HA OS 18.5 on `aarch64` (`rpi4-64`) — RAM split out as Q-30 |
| Q-6 | Do all RPC clients honour a configured `rpc_key`? | **Moot for v0.1:** `share_instance = No`, so RNS opens no RPC listener (verified); a random `rpc_key` is still rendered. Revisit in v0.3 if a shared instance is needed |
| Q-7 | Hot backup consistency of SQLite WAL while RNS runs | Open — Phase 1 test; `backup: cold` fallback |
| Q-8 | Can a bridged-network app use the HA Tailscale app's tailnet? | Open — Phase 1 test on device |
| Q-9 | First-run UX with no default remote | **Resolved in design:** [first-run UX](../ux/first-run.md), [ADR 0004](../adr/0004-public-peer-presets.md) |
| Q-10 | Long-run memory/CPU on Pi 4B on a real network | Open — Phase 1 soak test |
| Q-11 | Permissions needed to publish Supervisor discovery | Open — v0.2 |
| Q-12 | Launch `rnsd` vs a thin Python entry point | **Resolved (Phase 1):** thin entry point `meshbeacon.node` using the public `RNS.Reticulum` API (architecture §9) |
| Q-13 | Interoperability of Python RNS 1.6.x with Ratspeak servers and apps (Rust `rsReticulum`) | Open — **public release gate** (RG-10); not a local development blocker |
| Q-14 | How will MeshBeacon track RNS security fixes given the mirror-only upstream? | Open — maintainer |
| Q-15 | AI tool accounts' training setting | **Resolved:** training disabled on the maintainer's ChatGPT and Claude accounts |
| Q-16 | Stamp enforcement in RNS 1.6.2: pin policy and upgrade timing | Open — Phase 1 |
| Q-17 | GPL corresponding-source approach for base-image components | Recommendation made ([licensing §5.1](licensing.md#51-gpl-corresponding-source)); **public release gate** (RG-7) |
| Q-18 | Home Assistant brand-guideline constraints on icon and naming | Open — maintainer |
| Q-19 | Confirm base-image component licences from a generated SBOM | Open — SBOM in Phase 1 CI; **public release gate** (RG-7) |
| Q-20 | Copyright line wording in `NOTICE` | Open — maintainer (currently "The MeshBeacon contributors") |
| Q-21 | App slug | **Resolved:** `meshbeacon` |
| Q-22 | Tagline | **Resolved:** "Decentralised connectivity for your home." |
| Q-23 | Official trademark register searches (UK IPO, EUIPO, WIPO, USPTO, MyIPO) | Open — **public release gate** (RG-8) |
| Q-24 | Does `discover_interfaces` (receive-only) transmit anything about the local node? | Open — post-v0.1 |
| Q-25 | Exact passphrase character set that ConfigObj quotes safely | **Resolved (Phase 1):** printable ASCII 1–128, excluding `" ' # , % $ \` and leading/trailing spaces; verified by property-based round-trip tests |
| Q-26 | Should a data budget ever be *enforced* (not just warned about)? | Open — post-v0.1 |
| Q-27 | Is GitHub private vulnerability reporting enabled? | Open — **public release gate** (RG-11) |
| Q-28 | Will Ratspeak (and a second operator) agree to being listed as presets? | Open — **public release gate** (RG-10) |
| Q-29 | Courtesy contact with the existing MeshBeacon maintainers — outcome | Open — **public release gate** (RG-9) |
| Q-30 | Confirm the reference device's RAM | **Resolved:** 8 GB model, 7.6 GiB usable, 2.5 GiB swap ([reference environment](../testing/reference-environment.md)) |
| Q-34 | Is a lower-memory physical device (e.g. a 1–2 GB Raspberry Pi) available for occasional release testing, in addition to the enforced-limit container test? | Open — maintainer |
| Q-31 | Will the reference device move from Wi-Fi to Ethernet? | Open — maintainer; tests run on Wi-Fi meanwhile |
| Q-32 | Is the reference 5G connection behind CGNAT? | Open — maintainer |
| Q-33 | Does AdGuard Home serve DNS for apps on the reference device, and with which blocklists? | Open — maintainer; test C5–C8 |

## 15. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | RNS upstream single maintainer / mirror-only / no issue tracker | High | High | Pin exact versions; integrate only via public API; compatibility test suite against each new RNS release; thin core. |
| R-2 | Name confusion with the existing MeshBeacon organisation | High | Medium | ADR 0003 conditions and rename triggers; Q-21–Q-23, Q-29. |
| R-3 | Licence non-compliance in published images (missing notices, GPL source) | Medium | High | No image published until licensing O1–O7 are in CI; SBOM; licence allow-list. |
| R-4 | Community rejection over AI-assisted provenance | Medium | High | Open disclosure, human accountability, experimental labelling (§10.1); AI-tool rules (licensing §6.4). |
| R-5 | Breaking protocol change (stamp enforcement in 1.6.2) | High | Medium | Track RNS releases; integration tests across versions; clear upgrade notes. |
| R-6 | Resource exhaustion on the HA host | Low–Medium | High | Memory, CPU-priority, storage and log guards (architecture §4.3); soak tests. |
| R-7 | Private key exposure via permissions, backups or logs | Medium | High | §7.2 controls; non-root user; log redaction; secret scanning. |
| R-8 | Users enable transport and incur bandwidth/abuse on 5G | Medium | Medium | Off by default; plain explanation; counters and optional warning. |
| R-9 | Duplicated effort with an existing competitor | Medium | Low–Medium | Q-2. |
| R-10 | HA platform changes (add-on→app renames, builder migration) | Medium | Low | Follow HA developer blog; pin base images. |
| R-11 | **Silent identity loss** — RNS overwrites corrupt identities (verified) | Medium | High | MeshBeacon-owned atomic creation, pre-start validation, verified backup copy (architecture §4.6). |
| R-12 | **Configuration injection** via user fields (verified exploitable with naive templating) | Medium (if mishandled) | High | Architecture §4.1 layered validation; hostile-input suite. |
| R-13 | **Five-minute target missed** without verified presets | Medium | Medium | Clear docs for adding a peer; timed user test in acceptance; verify ≥ 2 operators early. |
| R-14 | **Preset operator dependency or failure** | Medium | Medium | ≥ 2 independent operators; presets as data; custom peers always available (ADR 0004). |
| R-15 | **Watchdog restart loops** if health reflects connectivity | Low (by design) | Medium | Health = process health only (architecture §4.4). |
