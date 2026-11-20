# M4 results: the standalone LXMF messaging engine

**Date:** 20 November 2026. **Branches:** `feature/m4-lxmf-engine` (WP1 to WP6, PR #7) and
`feature/m4-final-acceptance` (final acceptance evidence, stacked on it). **Versions:** RNS 1.6.0, LXMF
1.3.0 (unmodified, hash-pinned), Python 3.13. Isolated networks only (loopback, Docker `--network
none`); throwaway identities; no live Reticulum network and no Home Assistant installation was
used. No household identifiers are recorded (CLAUDE.md rule 15).

**Status: every automated M4 criterion passes, locally on the real base image and in CI. M4 is
not accepted.** Four items remain, and only the maintainer can run them: MS-14 (Sideband and
Ratspeak, on devices), MS-18 and the Pi half of MS-1 (the spare Pi), and IS-4's VM run. The dev
image's idle memory is above the +40 MiB criterion in a container; D-M4-7 decides it on the Pi.
See [Outstanding before acceptance](#outstanding-before-acceptance).

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
# MS-1 against v0.2: build main's app folder as the baseline, then compare (about 10 minutes)
git archive main meshbeacon | tar -x -C <empty-dir>
docker buildx build --load -t meshbeacon:v0.2-main <empty-dir>/meshbeacon
python3 tools/acceptance/ms1_baseline.py meshbeacon:v0.2-main meshbeacon:prod
```

Behind a TLS-intercepting proxy, add `--network host --secret id=build_ca,src=<proxy CA bundle>`
and the proxy as `--build-arg HTTPS_PROXY=…`. The Dockerfile does not change, and the secret is
never stored in the image. The final acceptance run below was built this way, on the **real,
digest-pinned Home Assistant base**, with the `apk` security-update layer.

**Local base-image substitution (WP1 to WP6 runs only).** That sandbox could not pull `ghcr.io` layers or reach the Alpine
CDN, so those local images were built from the same Dockerfile with the test-only stand-in base
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

## CI on the real base image (`29d3824`)

| Run | Result |
|---|---|
| CI run 78 | **All jobs green.** Lint, types and shell scripts. Unit and isolated-network integration tests, including the real-LXMF tests, with no network. Container tests on amd64 and aarch64 (QEMU) on the digest-pinned Home Assistant base. On amd64: the messaging tests on both images, unconfined; the development image **confined by AppArmor** (the production profile plus the engine's socket folder), with no denial; and the production image confined by the production profile |
| Release dry run 32 | **Green.** Both architectures built twice from scratch, reproducible, verified (labels, SBOM, provenance), including the new check that no layer holds the engine |
| CI run 77 (`1b7b529`) | **Failed, and led to a fix:** under AppArmor the setgid socket folder lost its setgid bit (the profile denies `CAP_FSETID`), so the core could not reach the engine. Fixed in `29d3824` with the `mb-msg` group |

Real-base idle memory (CI run 77, amd64): production 65.9 MiB, development image 109.9 MiB
(**+44.0 MiB**).

## Final acceptance run (`feature/m4-final-acceptance`)

This branch adds tests and evidence only: no product code, Dockerfile, AppArmor profile, option or
service changed. Local images were built from the unmodified Dockerfile on the **real** pinned base
(`ghcr.io/home-assistant/base-python:3.13-alpine3.24@sha256:c7d34ae2…`), with the `apk` layer.
Local host: amd64, 4 CPUs, cgroup v1, no AppArmor.

| Check | Where | Result |
|---|---|---|
| `ruff check`, `ruff format --check`, `mypy` (core, tests, tools) | local | Clean |
| Unit and isolated-network integration, real LXMF and `lxmd` (`-m "not container"`) | local | **515 passed, 1 skipped** (needs an unprivileged user), 9 min 46 s |
| Container suite, production and messaging-dev images (`-m container tests/container`) | local | **32 passed, 1 skipped** (AppArmor enforcement needs an AppArmor host: CI) |
| Home Assistant integration: `mypy --strict`, `pytest tests/ha` (Python 3.14) | local | Clean; **97 passed** |
| Panel and design-token tests (`node --test`) | local | **39 passed** |
| Release layout (`tools/check_release.py`) | local | Passed |
| MS-1 baseline against v0.2 (`tools/acceptance/ms1_baseline.py`) | local | See MS-1 below |
| CI run 83 (`35e31ce`) | CI | **All 7 jobs green**: lint, types, shell scripts, hadolint; unit and integration with no network; HA tests and the HA 2026.11.2 smoke test; container tests on amd64 and aarch64; on amd64 the messaging tests on both images, the dev image under AppArmor enforcement with no denial, licences, SBOM and both Grype gates; dependency and secret scanning |
| Release dry run 35 (`ca8bd91`) and 36 (`35e31ce`) | CI | **Green**: both architectures, built twice, reproducible, verified, no layer holding the engine |

ShellCheck and hadolint were not installed locally; no shell script or Dockerfile changed, and CI
runs both. CI runs 81 and 82 were cancelled by CI's concurrency rule when a newer commit arrived.

**WP5 additions** (`35e31ce`), on top of the WP5 checks already in place:

- **Tied to the sources:** a unit test maps every file the `messaging-dev` target adds (the
  engine's source and every file in `rootfs-messaging/`) and every program LXMF installs (`lxmd`)
  to its path in an image layer. It checks that release verification's `MESSAGING_PATHS` refuses
  each one. A new messaging file that the patterns miss now fails before a release. Checked: an
  extra `rootfs-messaging/` file makes the test fail.
- **Accounts in every layer:** the production layer scan reads each layer's `/etc/passwd` and
  `/etc/group` for `mb-lxmf` and `mb-msg`. Before, accounts were checked in the final file system
  only.
- **Positive control:** the same scans, and `verify_image.messaging_paths` itself, run on the
  development image's real layers. They find the engine, LXMF, `lxmd`, the service, the init
  script, the marker and both accounts, so their silence on production means absence.
- **Empirical diff** of the two real-base images: the development image adds 37 paths (excluding
  `__pycache__`), and the patterns match every one. The exception is the empty folder
  `/etc/meshbeacon`, which holds only the marker. The development image also adds `mb-lxmf` and
  `mb-msg` to `/etc/passwd` and `/etc/group`.

## Acceptance criteria

| ID | Result | Evidence |
|---|---|---|
| IS-1 | **Pass** (engine added) | Core 9100, Reticulum 9101, engine 9102, by real UID; no shared user or group |
| IS-2 | **Pass** | The engine holds no Supervisor token, status token or RPC key; its identity is `mb-lxmf` 0600 |
| IS-3 | **Pass** | Cross-user reads of identities, configs, queue and options fail; the socket serves only UID 9100 and the core accepts only 9102 (`SO_PEERCRED` both ways); `mb-rns` cannot reach the socket folder |
| IS-3a | **Pass** | `\0rns/meshbeacon` is present inside the app container and unreachable from containers on `none` and `bridge` networks; the RPC refuses a wrong key for `mb-lxmf` and `meshbeacon`; no RPC key in the engine's configuration |
| IS-4 | **Pass (CI and local); VM pending** | A weakened installation (folders and socket made world-accessible) is detected; the peer check still refuses `mb-rns`. Under AppArmor enforcement in CI (run 78) with a derived profile; the production profile is unchanged. The Supervisor-loaded profile on a VM is part of RG-13 |
| MS-1 | **Automated: pass. Pi: pending** (criterion: "Automated + Pi") | **Against v0.2, final run, same host, real base** (`tools/acceptance/ms1_baseline.py`; v0.2 = `main` at `80e9f59`, two runs each, 60 s settle, 120 s sample, every process in the container): memory 72.6 / 72.9 MiB (v0.2) vs 73.4 / 72.7 MiB (M4), **+0.3 MiB**; CPU 0.117 / 0.116 % vs 0.122 / 0.125 %, **+0.007 percentage points**; listening endpoints identical (TCP 8099, and the Unix socket of s6-overlay's `s6rc-oneshot-runner`); no `/data/messaging`. Earlier: no engine file, package, user, service or marker in the production file system **or in any layer** (`docker save` scan); `import meshbeacon.messaging` and `import LXMF` fail; no messaging option; no engine process, no `/data/messaging`, `share_instance = No`, no `@rns` socket. Idle memory 68.8 MiB (WP1 baseline 69.5 MiB, within ±2 MiB). Release verification (`verify_image.py`) refuses any layer holding the engine |
| MS-2 | **Pass** | Separate from the transport identity; replacing the transport identity leaves it unchanged; damaged copies are never replaced and the engine does not start (rule 13) |
| MS-3 | **Pass** | A reference LXMF peer reads the engine's announce with LXMF's public helpers: no display name and no stamp cost by default. Messages carry no fields; in "anyone" mode only the ticket field (`FIELD_TICKET`), and only to contacts |
| MS-4 | **Pass** | Unit tests: deletion on acknowledgement, retention cap, 16 MiB file cap under a flood |
| MS-5 | **Pass** | Direct delivery on loopback; one message for a repeated idempotency key |
| MS-6 | **Pass** | Recipient offline: `stored_on_node` through the unmodified `lxmd`, never `delivered`; the recipient later collects it; pending messages are resubmitted after a restart |
| MS-8 | **Pass** | Strangers refused and counted; unverifiable senders held, re-verified or refused; invalid signatures refused at once (unit) |
| MS-9 | **Pass (two negatives and positives)** | **No stamp at all** (`ca8bd91`): `inbound: anyone`, cost 8. The stranger's LXMF hears the cost, then forgets it (the public `LXMRouter.update_stamp_cost`, on the stranger's own router), so its message leaves with `LXMessage.stamp` `None`. It is **not accepted**, and nothing is counted as received. The same stranger's properly stamped message on the same path is accepted. With stamp enforcement turned off in the engine (a local mutation, not committed), the test fails. **Weak stamp:** cost 10, a stranger's stamp of value 1.37 to 1.52 (below 10, as reported by LXMF) is **not accepted**; the same stranger's properly stamped message is. A contact holding the engine's ticket is accepted with a weak stamp (ticket value 256). In both negatives the stranger's LXMF reported `delivered` |
| MS-10 | **Pass** | Over 8 KiB, invalid UTF-8, NUL, extra fields (counted, never kept) and floods above the rate limits; nothing crashes |
| MS-15 | **Pass** | `kill -9`: only the engine restarts; Reticulum keeps its process and the health endpoint never fails. `SIGSTOP` (hang): detected after three missed health checks, killed and restarted. An engine that cannot start backs off without touching Reticulum. Pause after five failures in 30 minutes (unit). It survives a Reticulum restart and reconnects by itself |
| MS-16 | **Pass** | A corrupt queue is quarantined and a fresh one started (unit). (The Home Assistant repair issue is M5) |
| MS-19 | **Pass** | Engine data tree, inotify: **0.20 writes/s idle, 0.50 writes/s** with one message each way every 20 s (only `queue.db-wal` and LXMF's `state.db-wal`) |
| MS-21 | **Pass** | Source checks: the engine imports no Home Assistant, HTTP-server or UI code; only `engine.py` imports LXMF; the binding, contract, queue and settings import neither LXMF nor RNS; nothing outside the engine imports it. The contract runs against the real engine directly (no binding) and over the socket |
| MS-14 | **Not run: acceptance blocker** | Needs Sideband 2.3.x and Ratspeak 1.1.x on devices on an isolated network |
| MS-18 | **Not run: acceptance blocker** | Spare Pi. Container readings: **+44.8 MiB** on the stand-in base (113.6 vs 68.8 MiB), **+44.0 MiB** on the real base in CI (109.9 vs 65.9 MiB) and **+44.0 MiB** on the real base locally in the final run (108.9 vs 64.9 MiB), all **above the +40 MiB criterion** (spike: 43.1 MiB). The app total (108.9 MiB) is within its 160 MiB limit. CPU and stamp time were not measured; they need the Pi. D-M4-7: decided on the Pi |

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
5. **Memory** (above): +44.0 to +44.8 MiB in a container.
6. **AppArmor for the dev image** is tested in CI only, with a profile derived from the production
   one plus `/run/meshbeacon-messaging/`; the dev image is never installed by the Supervisor. A
   future production engine needs that rule in the shipped profile, through review.
7. **The no-stamp sender is simulated.** The test's sender is the unmodified LXMF told, through
   its public API, to forget the cost it heard. It stands for any sender that never heard or
   ignores the cost. Whether Sideband and Ratspeak stamp correctly against the engine is MS-14's
   "stamped" case.
8. **The messaging engine is tested on amd64 only.** CI's aarch64 job runs the production container
   suite under QEMU but skips the messaging-dev steps. LXMF is pure Python, so its behaviour should
   be the same, but the engine has not run on arm64. The Pi (MS-18) will be the first run there.
9. **Sender-side "delivered" for refused messages** (both MS-9 negatives) is expected and documented
   (delivery semantics above): refusals are never signalled to the sender.

## Outstanding before acceptance

Every automated criterion in [the plan](../plans/m4-lxmf-engine.md#acceptance) passes. M4 is
accepted only when the maintainer has also recorded:

| Item | What is needed | Where it is recorded |
|---|---|---|
| **MS-14** | The interoperability matrix both ways with Sideband 2.3.x and Ratspeak 1.1.x on an isolated network: direct, opportunistic, propagated, stamped and offline cases. Q-43 (LXMF 1.3.0 against 1.3.1) is part of it | Manual, here |
| **MS-18** | On the reference Pi ([procedure](m4-pi-acceptance.md); decision P-1: the live Pi, not a spare one, without disturbing the installed app): idle memory added by messaging (criterion ≤ +40 MiB; containers read +44 MiB), the app ≤ 160 MiB, CPU added ≤ 0.5 % (basis: P-2), and a stamp at the recipient's cost in ≤ 30 s or a clear failure (Q-41). D-M4-7 decides the memory criterion | Pi, here |
| **MS-1 (Pi half)** | Idle memory and CPU with messaging off, unchanged from v0.2 on the Pi ([procedure](m4-pi-acceptance.md): Supervisor figures, since `ms1_baseline.py` needs Docker access, which the procedure does not use) | Pi, here |
| **IS-4 (VM half)** | The isolation tests under the Supervisor-loaded AppArmor profile on a VM (RG-13) | VM, here |

None of these can run in this sandbox or in CI. No further code change is known to be needed for
them, unless MS-18's memory fails on the Pi; D-M4-7 then sends the plan back for review.

## Deviations from the approved design

| Approved | As built | Why |
|---|---|---|
| Socket in `/run/meshbeacon-io/messaging/`, group `meshbeacon` (ADR 0018 point 6) | `/run/meshbeacon-messaging/engine.sock`, 0660, group `mb-msg` (only the core and the engine), folder `mb-lxmf:mb-msg` 0750 | `/run/meshbeacon-io/` is root:meshbeacon 0750 (the engine would have had to join the core's group); a setgid folder failed under AppArmor (no `CAP_FSETID`), found by CI |
| `SOURCE_UNKNOWN` held ≤ 10 minutes (T44, proposed) | 2 minutes, at most 50, with path requests | A path answer arrives in seconds; a shorter hold bounds memory |
| Core-side supervision in the core | Also present in production images, inert (`EngineSupervisor` is created only when the image's marker and the `messaging` service exist) | It is part of the core; tests prove nothing of the engine runs or exists in production |
| `s6-svperms` for named services | For every service that starts down | The production script names no messaging service |
| Tickets (T45) | Given to contacts only, in "anyone" mode | Needed for MS-9's "contacts with tickets are not charged" |
