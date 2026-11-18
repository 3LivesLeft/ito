# Architecture

Status: **Proposed (Phase 0)** · No application code exists yet. This describes the intended
structure so that Phase 1 can be reviewed against it.

Evidence and reasoning: [feasibility study](research/feasibility.md),
[ADR 0001](adr/0001-networking-foundation.md), [threat model](security/threat-model.md).

## 1. Goals that shape the architecture

1. **Reuse upstream.** RNS and LXMF do all protocol work. MeshBeacon configures, supervises,
   observes and presents.
2. **Separate the core from Home Assistant.** The core must run, and be tested, without Home
   Assistant (and in v1.0 as standalone Docker).
3. **Least privilege.** The HA app should earn the highest Supervisor security rating achievable.
4. **Fail safe and recover.** Losing connectivity, a crashed RNS process or a corrupt cache must
   never take down Home Assistant or silently change the node's identity.
5. **Small and readable.** A competent reviewer should be able to read the whole core in a
   sitting.

## 2. Component overview

```text
┌──────────────────────────── Home Assistant OS host ─────────────────────────────┐
│                                                                                 │
│  ┌──────────── HA Core ────────────┐        ┌──────── MeshBeacon app ─────────┐ │
│  │                                 │        │  (container, bridged network,   │ │
│  │  MeshBeacon integration (v0.2+) │  local │   AppArmor, no host network)    │ │
│  │  - config flow                  │  API   │                                 │ │
│  │  - sensors / binary sensors     │◄──────►│  meshbeacon-core (supervisor)   │ │
│  │  - notify platform (v0.3)       │ token  │   ├─ config renderer            │ │
│  │  - diagnostics (redacted)       │        │   ├─ process supervisor         │ │
│  └─────────────────────────────────┘        │   ├─ health & metrics collector │ │
│                                             │   ├─ local API (internal only)  │ │
│                                             │   └─ LXMF service (v0.3)        │ │
│                                             │            │ RPC (abstract sock)│ │
│                                             │            ▼                    │ │
│                                             │   RNS shared instance (child)   │ │
│                                             │   /data/reticulum (0700)        │ │
│                                             └────────────┬────────────────────┘ │
└──────────────────────────────────────────────────────────┼──────────────────────┘
                                                           │ outbound TCP only (v0.1)
                                                           ▼
                                         user-chosen Reticulum peers / tailnet / (I2P v0.4)
```

## 3. Layers and packages

| Layer | Package (proposed) | Depends on HA? | Responsibility |
|---|---|---|---|
| **Core** | `meshbeacon` (Python) | **No** | Validated settings model; RNS config rendering; RNS child-process supervision with back-off; health model; metrics collection via RNS RPC; identity and file-permission management; local API; (v0.3) LXMF send/receive. |
| **App adapter** | `app/` (Dockerfile, `config.yaml`, `run` script, `apparmor.txt`, translations) | Yes (Supervisor) | Map `/data/options.json` → core settings; set umask; start core; expose `watchdog`. Contains **no business logic**. |
| **Integration** (v0.2+) | `custom_components/meshbeacon` | Yes (HA Core) | Talk to the core's local API; create entities; notify platform; diagnostics. Contains **no Reticulum code** and never imports `RNS`. |
| **Standalone** (v1.0) | `docker/` | No | Same core, configured from a file/env instead of `options.json`. |

Rules:

- `meshbeacon` (core) must not import `homeassistant`, `bashio` or anything Supervisor-specific.
- The integration must not import `RNS` or `LXMF`. This keeps RNS's process-wide singleton and
  threads out of HA Core, and keeps HA Core's dependency tree free of `rns`.
- All cross-layer communication goes through one versioned local API with an explicit schema.

## 4. Core internals

### 4.1 Settings and config rendering

- A single typed settings model (proposed: dataclasses or pydantic — Phase 1 decision) validates
  every option. Unknown options are errors.
- MeshBeacon **renders RNS's `config` file from scratch** on every start. It never starts from
  RNS's default config (which enables `AutoInterface`) and never merges user-supplied RNS config
  text in v0.1.
- An **"advanced: raw RNS config" escape hatch** is deliberately *not* in v0.1. If added later,
  it must be opt-in and clearly flagged as bypassing MeshBeacon's safety defaults.
- Rendered config includes: unique `instance_name`, explicit random `rpc_key` (validated hex),
  `enable_transport` (default off), `[logging] loglevel` (≤4 by default), user-defined TCP client
  interfaces, and (opt-in) a TCP server interface bound to a chosen address.

### 4.2 Process supervision

- RNS runs as a **child process** of the core (not in the same interpreter), so a crash or
  memory leak in RNS can be contained, measured and restarted without restarting the app.
  (Whether the child is `rnsd` or a thin Python entry point is open — feasibility Q-12.)
- Restart policy: exponential back-off with a cap; a circuit-breaker state reported as unhealthy
  after N failures in M minutes.
- Memory guard: restart the child if its RSS exceeds a configurable ceiling (initial proposal
  256 MB). Measured idle RSS is ~55 MB (feasibility §9.1).
- Graceful shutdown on `SIGTERM` within the Supervisor `timeout`.

### 4.3 Health model

| State | Meaning |
|---|---|
| `starting` | Child launched, RPC not yet answering |
| `healthy` | RPC answering, ≥1 configured interface up (or none configured) |
| `degraded` | RPC answering, all configured interfaces down (e.g. internet lost) — **not** a restart trigger |
| `unhealthy` | RPC not answering, or circuit breaker open — restart / alert |

Loss of internet is `degraded`, not a failure: RNS's TCP client interfaces reconnect on their own
(verified: the test client retried and reconnected after 5 s).

### 4.4 Local API

- Bound **only** to the app's internal network address (the Supervisor-managed `hassio` network),
  never published as a host port by default.
- Authenticated with a random bearer token generated on first start (stored 0600) and handed to
  the integration via Supervisor discovery or manual entry (feasibility Q-11).
- Read-only in v0.1–v0.2 (health, interface stats). Write endpoints (send message, v0.3) are added
  only with explicit opt-in. v0.6 command execution follows the controls in the threat model.
- Never returns key material or the RPC key.

### 4.5 Storage layout (under `/data`)

```text
/data/
  options.json            # written by Supervisor
  meshbeacon/
    api_token             # 0600
    state.json            # 0600, non-secret runtime state
  reticulum/              # RNS --config dir, 0700
    config                # rendered each start, 0600 (contains rpc_key)
    storage/
      transport_identity  # 0600, RNS-managed private key
      known_destinations.db (+ -wal, -shm)
      cache/  resources/  blackhole/  identities/   # regenerable → backup_exclude
```

Permissions are set with `umask 077` and verified/repaired before each RNS start (RNS itself
creates files 0644 under the default umask — feasibility §7.1).

## 5. Networking posture

- `host_network: false`. Outbound TCP from the bridged container is sufficient for v0.1
  (CGNAT-safe). This also keeps RNS's abstract Unix sockets out of the host network namespace
  (feasibility §10, item 3).
- No published ports by default. An optional TCP listener (e.g. for a tailnet or LAN peer) is an
  explicit opt-in and must be documented as exposing a port.
- Disabled and not exposed in v0.1: `AutoInterface`, interface discovery, auto-connect,
  `discoverable`, `publish_ifac`, `location_cmd`, I2P, RNode.
- No default remote peer.

## 6. Dependency and build policy

- Python dependencies pinned **by version and hash** (e.g. `pip-compile --generate-hashes` or
  `uv lock`), installed with `--require-hashes`.
- Base image pinned by **digest** (`ghcr.io/home-assistant/base-python:…@sha256:…`, exact name
  to be confirmed in Phase 1).
- Multi-arch images (`aarch64`, `amd64`) built with the `home-assistant/builder` actions and
  **Cosign-signed**; SBOM generated per image.
- Reproducibility target: rebuilding the same commit yields the same installed package set and
  versions (byte-identical images are a stretch goal).

## 7. Evolution by version

| Version | Architectural additions |
|---|---|
| v0.1 | Core supervisor, config renderer, health, read-only local API, app wrapper |
| v0.2 | HA integration (custom component), metrics endpoints, diagnostics |
| v0.3 | LXMF service inside the core process family (separate child or within the RNS child — to decide), notify platform, optional propagation node (`lxmd` model) |
| v0.4 | Optional I2P: separate `i2pd` process/container with SAM, `I2PInterface` |
| v0.5 | RNode via `devices`/`uart` (explicit opt-in, lowers rating), LoRa parameters validated against regional limits |
| v0.6 | Authenticated command channel over LXMF with allowlist, replay protection, HA-side authorisation |
| v1.0 | Standalone Docker packaging of the same core |

## 8. What is deliberately not in the architecture

- No custom cryptography or protocol code.
- No cloud services, telemetry or analytics.
- No Docker socket, no privileged mode, no Supervisor `manager`/`admin` role.
- No write access to the Home Assistant configuration directory.
