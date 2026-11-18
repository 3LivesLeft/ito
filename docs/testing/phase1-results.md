# Phase 1 (v0.1.0 foundation) — verification results

Recorded: 18 November 2026 · Branch `feature/v0.1.0-foundation`

This record covers what was run in the development sandbox. **Nothing here is physical Raspberry
Pi validation**: the sandbox is x86-64, could not emulate aarch64, and could not pull the Home
Assistant base image. CI (`.github/workflows/ci.yaml`) repeats these checks against the real,
digest-pinned HA base image on both architectures; the reference-environment tests in
[strategy.md §6](strategy.md#6-reference-environment-testing-before-each-release) remain to be run
by the maintainer.

## 1. Environment

| Item | Value |
|---|---|
| Host | x86-64 Linux sandbox, Docker 29.10.0, cgroup v1, seccomp, **no AppArmor**, no binfmt/QEMU |
| Python (tests) | CPython 3.13.18 |
| Reticulum | `rns==1.6.0` from PyPI (unmodified) |
| Container base | **Test-only stand-in** (`tests/container/Dockerfile.localbase`: `python:3.13-alpine3.24` + checksum-verified s6-overlay 3.2.3.2, same `S6_*` settings), substituted for the pinned HA base with a BuildKit named context. The sandbox's egress policy denies `pkg-containers.githubusercontent.com`, so `ghcr.io` image layers cannot be pulled |

## 2. Automated results

| Suite | Where | Result |
|---|---|---|
| Lint: `ruff check`, `ruff format --check` | Sandbox | Pass |
| Type check: `mypy --strict` (14 modules) | Sandbox | Pass |
| `shellcheck` (s6 scripts, build helper) | Sandbox | Pass |
| Unit + integration (real, isolated RNS on loopback), including slow tests | Inside `docker run --network none` | **182 passed**, 0 failed (container tests excluded: 8) |
| Container tests (`tests/container`, internal Docker network) | amd64, stand-in base | **8 passed** |
| `pip-audit --require-hashes` of `meshbeacon/requirements.txt` | Sandbox | No known vulnerabilities |
| hadolint, gitleaks, SBOM + licence allow-list, image vulnerability scan, aarch64 build and tests | — | **Not run in the sandbox** — CI only |

Notable tests (all passing):

- **Injection:** Phase 0's naive-templating reproduction (newline in a host adding an
  `AutoInterface`), commas, `%(..)s` and `$` interpolation, quotes, control and bidi characters;
  property-based fuzzing (300 examples) of the renderer asserts the parsed structure is exact.
- **Identity:** truncated, empty, oversized and same-length (valid-key) corruption restored from the
  verified backup; both copies damaged → RNS never started and files left untouched; fingerprint
  mismatch; explicit replacement keeps the old identity and requires the option to be switched off;
  **1,000** randomised kills of the atomic-write primitive and **30** randomised kills of the real
  first-start step never left a partial identity or caused a later replacement.
- **Recovery:** crash loop gives up after bounded attempts with the health endpoint at `200`
  throughout; stalled child restarted; memory guard; start-history safe mode; the RNS child dies
  with the supervisor; in the container, killing the core stops the container instead of
  restarting it inside.
- **Connectivity vs health:** peer stopped → "cannot reach any of your peers", **no restart**, health
  `200`; peer back → reconnected with the same RNS process.
- **Isolation:** with default options the RNS process holds **no sockets at all**; in the container
  the only listener is the internal health port; no outbound connections.
- **Logs:** at the detailed level with transport on and an IFAC passphrase, no passphrase, RPC key,
  private key or 32-hex hash appears; RNS did print hashes and they were redacted.

### 2.1 CI on the real HA base image (run 10, commit `59c1f22`)

| Job | Result |
|---|---|
| Lint and type check (ruff, mypy --strict, shellcheck, hadolint) | Pass |
| Unit and isolated-network integration tests (`--network none`) | Pass (185 tests) |
| Container tests, amd64 (native) | 8 passed; idle memory **65.2 MiB** |
| Container tests, aarch64 (QEMU — **not** physical Pi validation) | 8 passed; memory read **130.3 MiB**, inflated by emulator overhead, so not a valid measurement |
| SBOM (86 packages) and licence allow-list | Pass |
| Image vulnerability scan (fail on critical) | Pass — no critical findings; 32 lower-severity findings remain, none with an Alpine fix that is not applied |
| pip-audit, gitleaks | Pass |

## 3. Defects found and fixed during verification

| Finding | How found | Fix |
|---|---|---|
| Any 64 bytes form a valid RNS key pair, so same-length corruption looks like a *different* identity | Unit test with `\xff` × 64 | Restore from backup when the backup matches the recorded fingerprint |
| A peer named `location_cmd` was refused (false positive in the forbidden-key check) | Property-based fuzzing | Check only setting keys, not section names |
| Child processes did not receive the data path, so `prepare` fell back to `/data` | Integration test | Pass `MESHBEACON_DATA`/`MESHBEACON_OPTIONS` explicitly |
| Killing the core left the RNS child running; s6 then started a second core and a second RNS on the same storage | Container test | `PR_SET_PDEATHSIG` in the child; `finish` stops the container on any crash |
| RNS output was block-buffered because `-I` ignores `PYTHONUNBUFFERED` | Network-isolated test run (the sandbox itself sets `PYTHONUNBUFFERED`) | Start every child with `-u`; regression tests in integration and container suites |
| Long file paths were redacted as if they were base64 | Integration output | Redact base64 runs only when they mix upper case, lower case and digits |
| The pinned HA base image ships zlib 1.3.2 (CVE-2026-4738, critical) and older krb5-libs and libexpat with high-severity CVEs | First CI image scan | Upgrade those packages in the Dockerfile with explicit minimum versions (zlib ≥ 1.4-r0, krb5-libs ≥ 1.22.3-r0, libexpat ≥ 2.10.0-r0); remove when the base image catches up. Remaining high-severity findings without an Alpine fix (OpenSSL 3.5.9, SQLite 3.53.4, Go stdlib in tempio, CPython 3.13.18) are tracked for the next base-image refresh |
| CI shellcheck (older) flagged `A && B \|\| C`; CI image lacked `pgrep`; licence check flagged base-image packages without SPDX metadata | First CI run | Explicit `if` blocks and pinned shellcheck; `/proc` scan in the test; reviewed licences recorded in `tools/check_licences.py` |

### 3.1 Review findings (independent review of PR #2)

| Finding | Evidence before the fix | Fix and evidence after |
|---|---|---|
| Interrupted identity **replacement** could end in needs_attention (crash after the new key reached primary and backup but before the state file; option then switched off), or generate a second new identity instead of finishing the first | New test `test_identity_replacement.py` failed 2 of 3 | Journalled replacement with a commit point; crash injected before each of the 6 writes, restarted with the option on and off: never needs_attention, never a silent change, never applied twice, original always kept — passes |
| The heartbeat was not refreshed during the prepare step (up to 180 s), so a slow start could make the health check fail and the Supervisor restart the app | `test_slow_preparation_keeps_health_ok` saw `503` | Wait for subprocesses while refreshing the heartbeat; prepare output goes to a temporary file. Health stays `200` through a slow and a timed-out preparation |
| L2 announce-flood test missing | — | Added (integration and container). With default RNS protections on the peer, only ≈ 2.5 kB reached MeshBeacon, so the test peer disables its announce cap and ingress control to forward everything: 3.1–3.3 MB delivered; Reticulum peak 42 MiB (integration), whole app 68.1 MiB under a 256 MB no-swap limit (container); logs within the rate limit; health `200` |
| The `integration` test marker was never applied (a `pytestmark` in `conftest.py` has no effect) | `-m integration` selected 0 tests | Marked through a collection hook: 21 tests |
| Simplifications | — | Removed a redundant redaction pattern; simplified a status-change condition with an unreachable branch; enum comparison instead of a string |

### 3.2 Reference Pi start-up failure (v0.1.0, commit `75060e3`)

| Item | Finding |
|---|---|
| Symptom | Builds and installs on the Pi (HA OS 18.5, Supervisor 2026.11.0), then exits at once: `/bin/sh: can't open '/init': Permission denied`, exit code 2; watchdog restarts about once a second |
| Root cause | The AppArmor profile granted `/init ix` and `/package/** ix` — execute without read. s6-overlay 3.2.3.2's `/init`, `preinit` and `stage0` are shell scripts, which `/bin/sh` must read. The HA example profile avoids this only through a blanket `file,` rule, which MeshBeacon's stricter profile had removed |
| Why the local `/init rix` edit did not help | The Supervisor loads an app's AppArmor profile only on install and on update to a new version; **Rebuild does not reload it** (verified in Supervisor 2026.11.0). The edit was most likely never loaded. Other s6-overlay scripts would have failed next in any case |
| Why `ha host logs` showed no denials | Not determined. `kernel` is among the default identifiers; when journald collects audit records itself they are usually filed under `audit`, which is not — an assumption to check with `ha host logs -t audit` |
| Why tests missed it | Docker on the development host and on CI runners never applies `apparmor.txt` (only the Supervisor loads it), and the sandbox kernel has no AppArmor. The profile was untested; the roadmap said so (LP-11), but the green container tests gave false confidence |
| Fix | Rewritten profile; version 0.1.1 so that Home Assistant offers an **Update**, which loads it |
| Regression tests | Static profile checks (unit); inventory of every executable in the image against the profile (container); CI loads the profile into a real AppArmor kernel in enforce mode and reruns the container tests confined, plus a test that confinement is active and restrictive |
| Confirmation on the Pi | After 0.1.0 with the maintainer's `/init rix` edit, the kernel log showed the next denial, `preinit` (requested `r`) — exactly as predicted. With the folder replaced by 0.1.1 and the app reinstalled, the app **started** on the Pi: s6-overlay, `cont-init` (exit 0) and the core (`MeshBeacon 0.1.1 starting (Reticulum 1.6.0, aarch64)`), identity created, isolated-node warning shown |
| Confirmation in CI | The 0.1.1 profile loaded into an Ubuntu runner's kernel in enforce mode; the container tests passed confined by it, including the confinement test |
| Denials remaining after the fix | CI's denial report (run 22, commit `1f59817`) showed three `capable` denials of `fsetid` for `chmod` on every start: root changing the mode of a file whose group it is not in (the init step, after handing `/data` to the service user) makes the kernel check `fsetid`, only to decide whether to keep a setgid bit. Harmless — the modes were applied and the tests passed — but they would hide real denials in the Pi's kernel log. 0.1.2 denies `fsetid` explicitly (never granted; explicit denials are not logged), and CI now **fails on any AppArmor denial** other than the two the confinement test provokes on purpose. Making that test stricter showed its exec-from-`/data` check had been ineffective: `docker exec` starts its first program before the profile applies, so the program ran (and failed only because renamed busybox found no applet). The check now starts the program from a confined shell. Processes inside the app are all confined, so the profile was not affected |
| Restart loop | The failure happens in s6-overlay before any MeshBeacon code runs, so MeshBeacon's start-history guard cannot act. The Supervisor bounds container restarts at 10 per 30 minutes ("Rate limit exceeded" afterwards, verified). Safeguards: catch profile errors before release (above); documentation now says to enable the watchdog only after a first successful start |

## 4. Resource measurements

| Measurement | Value | Conditions |
|---|---|---|
| Idle memory, whole app (RSS + swap of all `meshbeacon` processes) | **68.7 MiB** (core ≈ 25 MiB + Reticulum ≈ 44 MiB) | Container, amd64, stand-in base, no peers, after ~35 s |
| Same, in CI on the real HA base image | **65.2 MiB** amd64 (native); 130.3 MiB aarch64 under QEMU (emulator overhead — not valid) | CI run 10 |
| `docker stats` memory (cgroup) | 43.7 MiB | Same container |
| Idle CPU | ≈ 0.1 % | Same container |
| Starts under a hard 256 MB limit with no swap | Yes | Container test L1 |
| Announce flood under a hard 256 MB limit with no swap (L2) | App peak **68.1 MiB**; no OOM kill; 3.26 MB of announces delivered | Container, amd64, stand-in base (CI repeats on the HA base) |
| Image size | 117 MB uncompressed | Stand-in base; the HA base will differ |

Raspberry Pi figure: **not measured** (roadmap LP-16, RG-1). The emulated aarch64 reading is above the target only because of QEMU's overhead; that is an assumption until the physical measurement confirms it.

## 5. Not yet verified

- AppArmor on the Pi over a longer run (start-up is confirmed; check for denials after connecting a peer and enabling transport).
- Behaviour under the real Supervisor (watchdog, backups, options UI) — the image itself is now tested on the real HA base in CI.
- The physical Pi (maintainer); aarch64 has only been tested under emulation.
