# Threat model

Status: **Draft (Phase 0)** · Scope: v0.1.0 in detail; later versions in outline.
Method: assets → trust boundaries → threats (STRIDE) → controls. Verified facts reference the
[feasibility study](../research/feasibility.md).

## 1. Assets

| ID | Asset | Why it matters |
|---|---|---|
| A1 | **Transport identity private key** (`storage/transport_identity`, 64 raw bytes) | Defines the node's Reticulum identity; also the default RPC key seed. Compromise = impersonation and (with RPC) control of the instance. |
| A2 | LXMF delivery identity (v0.3) | Decrypts messages addressed to the user. |
| A3 | RNS RPC key and local API token | Control of the RNS instance / MeshBeacon API. |
| A4 | Home Assistant itself (availability, data, configuration) | MeshBeacon must not become a path into HA. |
| A5 | User's IP address, approximate location, network topology | Privacy. |
| A6 | Message content and metadata (v0.3) | Privacy. |
| A7 | Host resources (RAM, CPU, SSD, 5G data allowance) | HA availability; user's bill. |
| A8 | The shared Reticulum network | Good network citizenship; others' service. |
| A9 | Supply chain (images, dependencies, CI secrets) | Trust in every installation. |

## 2. Trust boundaries

```text
 [Internet / Reticulum peers] ──B1── [MeshBeacon container: core ── RNS child]
                                              │ B2 (local API, hassio network)
                                              ▼
                                        [HA Core + MeshBeacon integration]
                                              │ B3 (HA users, automations)
 [Other apps on host] ──B4── (namespaces, abstract sockets)
 [Supervisor / backups] ──B5── /data
 [CI, registry, PyPI] ──B6── image build
```

## 3. Threats and controls (v0.1)

| ID | Boundary | STRIDE | Threat | Control | Status |
|---|---|---|---|---|---|
| T1 | B5 | I | Private key world-readable inside container (RNS writes 0644 under default umask — **verified**) | `umask 077`; verify/repair 0600/0700 before every RNS start; test asserts permissions | Planned |
| T2 | B5 | I | Private key in unencrypted HA backup | Document; recommend encrypted backups; opt-in key export only | Planned |
| T3 | — | I | Private key or RPC key printed to logs | Never log key material; RNS loglevel ≤4 by default; log redaction filter for hex blobs of key length; test grep of logs in CI | Planned |
| T4 | B4 | S/E | Other host-network processes connect to RNS abstract sockets (`@rns/<name>`, `@rns/<name>/rpc` — **verified**) | `host_network: false` (container's own netns); unique `instance_name`; explicit random `rpc_key` | Planned |
| T5 | B4 | E | RPC key derivable from identity file (default behaviour — **verified**) | Explicit `rpc_key`, validated (invalid values silently fall back — **verified**) | Planned |
| T6 | B1 | I | IP leak to a default/bootstrap peer | No default remote; user chooses peers; docs explain exposure | Planned |
| T7 | B1 | I | Publishing gateway address/location via interface discovery | Discovery, `discoverable`, `publish_ifac`, `location_cmd` never rendered in v0.1 | Planned |
| T8 | B1 | T/E | Auto-connecting to untrusted discovered interfaces | `autoconnect_discovered_interfaces` never rendered; `AutoInterface` off | Planned |
| T9 | B1 | D | Announce/path-request floods exhaust memory/CPU | Transport off by default; RNS native filters/stamps/ingress control when on; RSS watchdog | Planned |
| T10 | B1 | D | 5G data exhaustion as a transport node | Transport opt-in with warning; byte counters (v0.2) | Planned |
| T11 | B2 | S | Unauthenticated access to local API | Bearer token, internal network only, no published port, read-only in v0.1 | Planned |
| T12 | B2 | E | Integration gains more HA permissions than needed | App has no `homeassistant_api`/`hassio_api` in v0.1 | Planned |
| T13 | B4 | E | Container escape / host compromise | No privileged mode, no extra capabilities, AppArmor profile, no Docker socket, non-root user inside container where feasible | Planned |
| T14 | B6 | T | Malicious or compromised dependency / base image | Hash-pinned deps, digest-pinned base, Cosign-signed images, SBOM, Dependabot/Renovate with review, vulnerability scanning | Planned |
| T15 | B6 | I | Secrets leaked in repo or CI | Secret scanning (GitHub + gitleaks in CI), minimal CI permissions, no long-lived tokens | Planned |
| T16 | — | R | Silent identity regeneration changes node address | Refuse to start if a previously existing identity is missing/corrupt unless user opts in | Planned |
| T17 | B1 | T | Malicious peer exploits RNS parsing bug | Track RNS releases; pin and upgrade promptly; container hardening limits blast radius | Accepted residual risk |
| T18 | — | — | Upstream RNS unmaintained / slow security fixes (mirror-only — **verified**) | Monitoring of releases; compatibility tests; ADR review trigger | Accepted residual risk |

## 4. Later versions (outline)

- **v0.3 messaging:** A2/A6. Store LXMF identity 0600; no message content in logs or HA
  diagnostics; notifications are encrypted end-to-end by LXMF, but **HA itself sees plaintext**
  when it composes them — document this. Propagation node is opt-in (stores others' encrypted
  messages; disk quota required).
- **v0.4 I2P / public gateway:** separate I2P router process, explicit opt-in; public gateway
  requires RNS native filters, stamps enforcement, blackhole sources, and a clear statement of
  exposure.
- **v0.5 RNode:** device access (`uart`/`devices`) lowers isolation; validate LoRa parameters
  against regional regulations (UK: Ofcom IR 2030 for 868 MHz — **[Assumption]**, confirm) to
  avoid unlawful transmission.
- **v0.6 remote commands (highest risk):** commands arrive from the mesh and act on the home.
  Required controls, all mandatory and off by default:
  - sender authentication by LXMF source identity (cryptographically verified by LXMF) **and**
    an explicit allowlist of identities;
  - per-command allowlist mapping to specific HA actions — no free-form service calls, no
    templates, no shell;
  - replay protection: monotonic counters or nonce + timestamp window, persisted;
  - rate limiting, audit log in HA, optional confirmation step for sensitive actions;
  - least-privilege HA token scoped to the allowed actions (**[Open]** HA long-lived tokens are
    not scope-limited — design needed);
  - no locks/alarms/safety-critical actions by default; documentation of the Reticulum License
    harm condition.

## 5. Privacy commitments

- No telemetry, analytics, crash reporting or "phone home" of any kind.
- No outbound connection that the user has not configured (except image pulls by the Supervisor).
- Diagnostics downloads redact identities, addresses, peer hostnames and tokens by default.

## 6. Review

This model must be revisited at every minor version and before v1.0's external security audit.
