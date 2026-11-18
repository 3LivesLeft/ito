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

## 4. Resource measurements

| Measurement | Value | Conditions |
|---|---|---|
| Idle memory, whole app (RSS + swap of all `meshbeacon` processes) | **68.7 MiB** (core ≈ 25 MiB + Reticulum ≈ 44 MiB) | Container, amd64, stand-in base, no peers, after ~35 s |
| `docker stats` memory (cgroup) | 43.7 MiB | Same container |
| Idle CPU | ≈ 0.1 % | Same container |
| Starts under a hard 256 MB limit with no swap | Yes | Container test L1 |
| Image size | 117 MB uncompressed | Stand-in base; the HA base will differ |

aarch64 and Raspberry Pi figures: **not measured** (roadmap LP-16, RG-1).

## 5. Not yet verified

- AppArmor profile (no AppArmor on the sandbox host) — must be checked on the Pi in complain mode.
- Behaviour under the real HA base image and Supervisor (watchdog, backups, options UI).
- aarch64 image build and tests (CI, emulated) and the physical Pi (maintainer).
- Low-memory profile L2 (announce flood under the limit) — test not yet written.
- SBOM licence check against a real SBOM; image vulnerability scan; gitleaks; hadolint (CI).
