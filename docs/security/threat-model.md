# Threat model

Status: **Draft — revised after independent review** · Scope: v0.1.0 in detail; later versions
in outline. Method: assets → trust boundaries → threats (STRIDE) → controls. Verified facts
reference the [feasibility study](../research/feasibility.md) and
[architecture](../architecture.md).

> **The Supervisor security rating of 8 is a target, not proof of security.** It is computed from
> a handful of declared settings (AppArmor profile, ports, host network, capabilities, API roles,
> signing). It says nothing about the correctness of MeshBeacon's code, its input validation, its
> handling of secrets, or the security of RNS. Security claims must rest on the controls and tests
> below and, before v1.0, on an external audit.

## 1. Assets

| ID | Asset | Why it matters |
|---|---|---|
| A1 | **Transport identity private key** (`storage/transport_identity`, 64 raw bytes) | Node identity when transport is on; default RPC-key seed. Compromise = impersonation; loss = new node address. |
| A2 | LXMF delivery identity (v0.3) | Decrypts messages addressed to the user. |
| A3 | RNS RPC key; IFAC passphrases for private peers; (v0.2) local API token | Control of the RNS instance; access to private networks. |
| A4 | Home Assistant itself (availability, data, configuration) | MeshBeacon must not become a path into, or a burden on, HA. |
| A5 | User's IP address, approximate location, network topology | Privacy. |
| A6 | Message content and metadata (v0.3) | Privacy. |
| A7 | Host resources (RAM, CPU, SSD space and wear, 5G data allowance) | HA availability; the user's bill. |
| A8 | The shared Reticulum network | Good network citizenship. |
| A9 | Supply chain (images, dependencies, CI secrets) | Trust in every installation. |

## 2. Trust boundaries

```text
 [Public / private Reticulum peers] ──B1── [MeshBeacon container: init(root) → core → RNS child (meshbeacon user)]
 [HA UI: user-entered options] ──B7──► /data/options.json ──► init/core
 [Supervisor: watchdog, backups] ──B5── /data, health endpoint
 [Other apps on host] ──B4── namespaces, abstract sockets
 [HA Core + integration (v0.2)] ──B2── local API
 [CI, registry, PyPI, AI tools] ──B6── source and image build
```

## 3. Threats and controls (v0.1)

| ID | Boundary | STRIDE | Threat | Control | Status |
|---|---|---|---|---|---|
| T1 | B5 | I | Private key world-readable inside the container (RNS writes 0644 — **verified**) | `umask 077`; init repairs 0600/0700 before each start; non-root service user; tests | Planned |
| T2 | B5 | I | Private key in an unencrypted HA backup | Document; recommend encrypted backups | Planned |
| T3 | — | I | Key material, RPC key or passphrases in logs | Never log them; RNS log level ≤ 4 by default; redaction filter on forwarded RNS output; CI log grep | Planned |
| T4 | B4 | S/E | Other host-network processes reach RNS abstract sockets (**verified** behaviour) | `host_network: false`; unique `instance_name`; explicit `rpc_key` | Planned |
| T5 | B4 | E | RPC key derivable from the identity file; invalid `rpc_key` silently falls back (**verified**) | Generate and validate the hex key ourselves before rendering | Planned |
| **T6** | B1 | I | **IP address and traffic volume visible to public peer operators** | No default peer; opt-in presets with privacy notice; custom peers always available ([ADR 0004](../adr/0004-public-peer-presets.md)) | Planned |
| T7 | B1 | I | Publishing gateway address/location via interface discovery | Discovery options never rendered in v0.1 | Planned |
| T8 | B1 | T/E | Auto-connecting to untrusted discovered interfaces; LAN discovery | Never rendered; `AutoInterface` off | Planned |
| T9 | B1 | D | Announce/path-request floods exhaust memory/CPU | Transport off by default; RNS native ingress control/announce cap; RSS watchdog; `nice` | Planned |
| T10 | B1 | D | 5G data exhaustion as a transport node | Transport opt-in with explanation; byte counters; optional data warning | Planned (warning only) |
| T11 | B2 | S | Unauthenticated local API (v0.2) | Not present in v0.1; v0.2: token, internal network only, no published port | Deferred |
| T12 | B2 | E | Excess HA permissions | No `homeassistant_api`, `hassio_api`, `auth_api` in v0.1 | Planned |
| **T13** | B4 | E | Container escape or host compromise; compromise of a root process | Non-root `meshbeacon` user for core and RNS; root limited to a small init step; no extra capabilities; AppArmor profile; no Docker socket | Planned |
| T14 | B6 | T | Malicious or compromised dependency or base image | Hash-pinned deps; digest-pinned base; signed images; SBOM; vulnerability scanning; reviewed dependency updates | Planned |
| T15 | B6 | I | Secrets leaked in repository or CI | GitHub secret scanning + push protection; gitleaks in CI; minimal CI token permissions | Planned |
| **T16** | B5 | R/D | **Silent identity replacement**: RNS overwrites a corrupt identity with a new one (**verified**) — e.g. after a power cut during first write | MeshBeacon creates the identity atomically; validates before every start and never starts RNS on failure; verified backup copy; identity-hash tracking; explicit regenerate option only (architecture §4.6) | Planned |
| **T17** | B7 | T/E | **Configuration injection** via peer name, host, network name or passphrase — newline injects a new interface, comma creates a list, `%(..)s` interpolates (**verified**) | Schema regex; core allow-list validation; ConfigObj object API only; round-trip structural check; hostile-input test suite (architecture §4.1) | Planned |
| **T18** | B5 | D | **Watchdog restart storm** if health is tied to internet connectivity (Supervisor restarts the app after 2 failed checks — **verified**) | Health endpoint reports process health only; connectivity reported separately (architecture §4.4) | Planned |
| **T19** | — | D | **Log flooding** fills journald / wears SSD | Rate-limited log forwarding; level ≤ 4; periodic summaries instead of per-event lines | Planned |
| **T20** | B5 | D | **Storage exhaustion** on `/data` (cache, resources, SQLite growth) | Free-space checks; size caps on regenerable directories; soak test | Planned |
| **T21** | B1 | D | **Dependence on one preset operator**, or a preset operator going rogue or offline | ≥ 2 independent verified operators before presets ship; presets are data and can be removed; custom peers always available | Planned |
| **T22** | B1 | S | **Tampered or incorrect preset data** (wrong host/port) | Presets reviewed in pull requests, verified V1–V7 before each release, shipped inside the signed image | Planned |
| T23 | B1 | T | Malicious peer exploits an RNS parsing bug | Track RNS releases; container hardening limits blast radius | Accepted residual risk |
| T24 | — | — | Upstream RNS unmaintained or slow to fix (mirror-only — **verified**) | Release monitoring; compatibility tests; ADR 0001 review triggers | Accepted residual risk |
| **T26** | B4 | I/E | **High-privilege co-installed apps** (e.g. an SSH/terminal app with protection mode disabled) can reach the Docker daemon and read any app's `/data`, including the identity (**[Assumption]**) | Outside MeshBeacon's control: documented in `DOCS.md` and SECURITY.md; recommend keeping protection mode enabled | Accepted residual risk (documented) |
| **T27** | B1 | I/D | **DNS resolver** (e.g. AdGuard Home) logs peer lookups or blocks a peer hostname | Document; plain "cannot resolve" message with no restart loop; reference tests C5–C8 | Planned |
| **T25** | B6 | — | **AI-tool data use**: RNS source given to an AI tool whose provider trains on inputs would risk breaching the Reticulum License's AI condition | Project rules in licensing §6.4: training opted out; documentation rather than source; no datasets | Planned (process control) |

## 4. Later versions (outline)

- **v0.2 local API and integration:** token authentication, internal network only, read-only
  until v0.3; redacted diagnostics; identity import with validation and confirmation.
- **v0.3 messaging:** LXMF identity 0600; no message content in logs or diagnostics; document that
  HA composes notifications in plaintext before LXMF encrypts them; propagation node opt-in with
  disk quota.
- **v0.4 I2P / public gateway:** separate I2P router; public gateway only with RNS native filters,
  stamps enforcement, blackhole sources and a clear exposure statement.
- **v0.5 RNode:** device access lowers isolation; validate LoRa parameters against regional rules
  (UK 868 MHz: Ofcom IR 2030 — **[Assumption]**, to confirm).
- **v0.6 remote commands (highest risk):** sender authentication by LXMF identity *and* allowlist;
  per-command allowlist mapped to fixed HA actions (no free-form service calls, templates or
  shell); persisted replay protection; rate limiting; audit log; optional confirmation; no
  safety-critical actions by default; external design review before implementation.

## 5. Privacy commitments

- No telemetry, analytics, crash reporting or "phone home" of any kind.
- No outbound connection that the user has not configured (apart from the Supervisor pulling
  images).
- Status messages and diagnostics contain no identity hashes, passphrases or tokens; peer
  hostnames appear in the app log (which the user controls) but are redacted from any future
  shareable diagnostics file.

## 6. Vulnerability reporting

Private vulnerability reporting through GitHub must be **enabled** on the repository by the
maintainer (Settings → Code security → Private vulnerability reporting). Its current state could
not be checked from the research environment — see [SECURITY.md](../../SECURITY.md) and
feasibility Q-27.

## 7. Review

Revisit this model at every minor version, whenever a permission or default changes, and before
the v1.0 external security audit.
