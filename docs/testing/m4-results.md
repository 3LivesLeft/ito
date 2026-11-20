# M4 results: the standalone LXMF messaging engine

**Date:** 20 November 2026. **Branch:** `feature/m4-lxmf-engine`. **Versions:** RNS 1.6.0, LXMF
1.3.0 (unmodified, hash-pinned), Python 3.13. Isolated networks only (loopback, Docker `--network
none`); throwaway identities; no live Reticulum network and no Home Assistant installation was
used. No household identifiers are recorded (CLAUDE.md rule 15).

**Status: development-complete. M4 is not accepted:** MS-14 (Sideband and Ratspeak, on devices)
and MS-18 (the spare Pi) are manual acceptance blockers, and the dev image's idle memory exceeds
the +40 MiB criterion in a container (see below; D-M4-7 decides it on the Pi).

## How to reproduce

```sh
# Images. The release dry run and the app store build the default target, which is production.
docker buildx build --load -t meshbeacon:prod meshbeacon
docker buildx build --load --target messaging-dev -t meshbeacon:messaging-dev meshbeacon
# Unit and isolated-network integration tests (real LXMF and lxmd on loopback)
.venv/bin/pytest -m "not container"
# Container tests: both images
MESHBEACON_IMAGE=meshbeacon:prod MESHBEACON_MESSAGING_IMAGE=meshbeacon:messaging-dev \
    .venv/bin/pytest -m container tests/container -s -rA
```

**Local base-image substitution.** This sandbox cannot pull `ghcr.io` layers or reach the Alpine
CDN, so the local images were built from the same Dockerfile with the test-only stand-in base
(`tests/container/Dockerfile.localbase`: `python:3.13-alpine3.24` and checksum-verified
s6-overlay 3.2.3.2) and without the `apk` security-update layer, as in earlier phases. **CI builds
the real Dockerfile on the real, digest-pinned Home Assistant base** and runs the same tests there,
on amd64 also under AppArmor enforcement. Local image IDs (stand-in base):
production `sha256:c5c553ded482…`, messaging-dev `sha256:d7c33c7a68bc…`.

## Results (local, images built at `855fcfd`; the later commit changes tests and documents only)

| Suite | Result |
|---|---|
| Full unit and isolated-network integration (`-m "not container"`) | 511 passed, 2 failed, 1 skipped. The two failures were pin tests that did not expect stage names on `FROM` lines; fixed (a stricter check: every stage builds on a pinned image or an earlier stage, and the last is production) |
| Re-run after the fixes: all unit tests and the 15 real-LXMF tests | 475 passed, 1 skipped (needs an unprivileged user) |
| Container suite on the production image (every existing test and the production-exclusion tests) | 29 passed, 1 skipped (AppArmor enforcement: CI only) |
| Messaging container tests on both images, final version | 16 passed |

## Acceptance criteria

| ID | Result | Evidence |
|---|---|---|
| IS-1 | **Pass** (engine added) | Core 9100, Reticulum 9101, engine 9102, by real UID; no shared user or group |
| IS-2 | **Pass** | The engine holds no Supervisor token, status token or RPC key; its identity is `mb-lxmf` 0600 |
| IS-3 | **Pass** | Cross-user reads of identities, configs, queue and options fail; the socket serves only UID 9100 and the core accepts only 9102 (`SO_PEERCRED` both ways); `mb-rns` cannot reach the socket folder |
| IS-3a | **Pass** | `\0rns/meshbeacon` is present inside the app container and unreachable from containers on `none` and `bridge` networks; the RPC refuses a wrong key for `mb-lxmf` and `meshbeacon`; no RPC key in the engine's configuration |
| IS-4 | **Pass locally; CI pending** | A weakened installation (folders and socket made world-accessible) is detected; the peer check still refuses `mb-rns`. AppArmor enforcement for the dev image runs in CI with a derived profile; the production profile is unchanged |
| MS-1 | **Pass** | No engine file, package, user, service or marker in the production file system **or in any layer** (`docker save` scan); `import meshbeacon.messaging` and `import LXMF` fail; no messaging option; no engine process, no `/data/messaging`, `share_instance = No`, no `@rns` socket. Idle memory 68.8 MiB (WP1 baseline 69.5 MiB, within ±2 MiB). Release verification (`verify_image.py`) refuses any layer holding the engine |
| MS-2 | **Pass** | Separate from the transport identity; replacing the transport identity leaves it unchanged; damaged copies are never replaced and the engine does not start (rule 13) |
| MS-3 | **Pass** | A reference LXMF peer reads the engine's announce with LXMF's public helpers: no display name and no stamp cost by default. Messages carry no fields; in "anyone" mode only the ticket field (`FIELD_TICKET`), and only to contacts |
| MS-4 | **Pass** | Unit tests: deletion on acknowledgement, retention cap, 16 MiB file cap under a flood |
| MS-5 | **Pass** | Direct delivery on loopback; one message for a repeated idempotency key |
| MS-6 | **Pass** | Recipient offline: `stored_on_node` through the unmodified `lxmd`, never `delivered`; the recipient later collects it; pending messages are resubmitted after a restart |
| MS-8 | **Pass** | Strangers refused and counted; unverifiable senders held, re-verified or refused; invalid signatures refused at once (unit) |
| MS-9 | **Pass (negative and positive)** | `inbound: anyone`, cost 10: a stranger's message with a stamp of value 1.37 (below 10, as reported by LXMF) is **not accepted**; the same stranger's properly stamped message is; a contact holding the engine's ticket is accepted with a weak stamp (ticket value 256) |
| MS-10 | **Pass** | Over 8 KiB, invalid UTF-8, NUL, extra fields (counted, never kept) and floods above the rate limits; nothing crashes |
| MS-15 | **Pass** | `kill -9`: only the engine restarts; Reticulum keeps its process and the health endpoint never fails. `SIGSTOP` (hang): detected after three missed health checks, killed and restarted. An engine that cannot start backs off without touching Reticulum. Pause after five failures in 30 minutes (unit). It survives a Reticulum restart and reconnects by itself |
| MS-16 | **Pass** | A corrupt queue is quarantined and a fresh one started (unit). (The Home Assistant repair issue is M5) |
| MS-19 | **Pass** | Engine data tree, inotify: **0.20 writes/s idle, 0.50 writes/s** with one message each way every 20 s (only `queue.db-wal` and LXMF's `state.db-wal`) |
| MS-21 | **Pass** | Source checks: the engine imports no Home Assistant, HTTP-server or UI code; only `engine.py` imports LXMF; the binding, contract, queue and settings import neither LXMF nor RNS; nothing outside the engine imports it. The contract runs against the real engine directly (no binding) and over the socket |
| MS-14 | **Not run: acceptance blocker** | Needs Sideband 2.3.x and Ratspeak 1.1.x on devices on an isolated network |
| MS-18 | **Not run: acceptance blocker** | Spare Pi. Container reading: dev image 113.6 MiB vs production 68.8 MiB, so **+44.8 MiB, above the +40 MiB criterion** (spike: 43.1 MiB). D-M4-7: decided on the Pi |

## Delivery semantics (what each state proves)

| Observation | What it means |
|---|---|
| `delivered` | The recipient's LXMF returned a delivery proof. **Not** that its application accepted, showed or read the message |
| `stored_on_node` | A propagation node accepted it for storage. It has not reached the recipient, and the engine is not told if it does |
| An inbound message | Its signature was validated by LXMF, its stamp met the cost where one applies, and it passed the engine's policy |
| **Observed (MS-9):** the stranger's LXMF reported **"delivered"** for the under-stamped message that the engine never accepted | Transport delivery is not application acceptance. Refusals are counted, never signalled to the sender |

The meanings are in `contract.STATE_MEANINGS` and tested. Log lines and reasons use the same words
(for example `rejected` says "refused by node" or "transfer refused", not "rejected by recipient").

## Findings and limitations

1. **No RPC key for the engine (IS-3a holds).** Sending, receiving, restarts and the use of a
   configured propagation node work without it. RNS then logs failed "destination used" updates and
   drops link identifications it cannot check against the node's blackhole list (fails closed).
   **Consequence for the future:** hosting a propagation node in the engine is not possible as
   designed (an `lxmd` without the key answered "no identity received"); recorded in ADR 0012.
2. **RNS log noise at engine start:** "Could not load known destinations from shared instance
   database" (a client cannot read the node's cache). Harmless; the engine requests its contacts'
   paths instead. Every engine line passes the core's redaction; no 32-hex string reaches the log
   (tested).
3. **Shutdown order.** At a container stop s6-overlay stops every service at once; the engine exits
   cleanly on SIGTERM (exit 0, socket removed, queue intact, identity unchanged on restart). The core
   stops it before Reticulum only when the core itself stops. The `s6-svwait: timed out` line at a
   container stop is present in production too and predates M4.
4. **Stamp cost and CPU.** A cost-14 stamp did not finish within two minutes in this sandbox, so
   the tests use cost 10. Q-41 and MS-18 (stamp ≤ 30 s at the recipient's cost) need the Pi.
5. **Memory** (above): +44.8 MiB in a container.
6. **AppArmor for the dev image** is tested in CI only, with a profile derived from the production
   one plus `/run/meshbeacon-messaging/`; the dev image is never installed by the Supervisor.

## Deviations from the approved design

| Approved | As built | Why |
|---|---|---|
| Socket in `/run/meshbeacon-io/messaging/`, group `meshbeacon` (ADR 0018 point 6) | `/run/meshbeacon-messaging/engine.sock`, 0660, group `mb-msg` (only the core and the engine), folder `mb-lxmf:mb-msg` 0750 | `/run/meshbeacon-io/` is root:meshbeacon 0750 (the engine would have had to join the core's group); a setgid folder failed under AppArmor (no `CAP_FSETID`), found by CI |
| `SOURCE_UNKNOWN` held ≤ 10 minutes (T44, proposed) | 2 minutes, at most 50, with path requests | A path answer arrives in seconds; a shorter hold bounds memory |
| Core-side supervision in the core | Also present in production images, inert (`EngineSupervisor` is created only when the image's marker and the `messaging` service exist) | It is part of the core; tests prove nothing of the engine runs or exists in production |
| `s6-svperms` for named services | For every service that starts down | The production script names no messaging service |
| Tickets (T45) | Given to contacts only, in "anyone" mode | Needed for MS-9's "contacts with tickets are not charged" |
