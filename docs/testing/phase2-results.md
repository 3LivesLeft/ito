# v0.2.0 (monitoring and observability): verification results

Recorded: 18 November 2026 · Branch `feature/v0.2.0-observability`

## Branch dependency

| | |
|---|---|
| Based on | `192db5f`, the reviewed head of PR #2 (`feature/v0.1.0-foundation`, v0.1.2). `main` at `3f3b35d` merged that same tree, so the branch also applies cleanly to `main` |
| Isolation | Nothing here was pushed to `feature/v0.1.0-foundation` or `main`. PR #2 is unaffected |
| Rebase rule | If PR #2's code changes after review (for example a fix found by the Pi soak), rebase this branch onto the new head and rerun everything below. If PR #2 is reverted from `main`, retarget this branch's PR at `feature/v0.1.0-foundation` |
| Merge order | Not before PR #2's physical tests and independent review are complete, and ADR 0006 is approved |
| Running Pi | Untouched. It still runs 0.1.1; nothing from this branch has been installed |

## Environment

| Item | Value |
|---|---|
| Host | x86-64 Linux sandbox, Docker 29.10.0, cgroup v1, **no AppArmor**, no QEMU |
| Core tests | CPython 3.13.18, `rns==1.6.0` (PyPI, unmodified) |
| Integration tests | CPython 3.14, Home Assistant **2026.10.4** via `pytest-homeassistant-custom-component==0.13.375` |
| Container base | **Test-only stand-in** (`tests/container/Dockerfile.localbase`), because `ghcr.io` blobs are blocked here. The build also used a test-only copy of the Dockerfile without the `apk add --upgrade` security line, because the Alpine CDN is blocked here. Runtime wheels were installed hash-pinned as normal. CI builds the real Dockerfile on the real base |

## Results

| Suite | Result |
|---|---|
| ruff (core, integration, tests, tools), ruff format | Pass |
| mypy `--strict`, core (16 modules, Python 3.13) | Pass |
| mypy `--strict`, integration (9 modules, Python 3.14, against HA's types) | Pass |
| shellcheck (run script) | Pass |
| Unit + isolated real-RNS integration tests, slow tests included | **226 passed** |
| Home Assistant integration tests (`tests/ha`) | **25 passed** |
| Container tests (amd64, stand-in base, unconfined) | **12 passed**, 1 skipped (AppArmor confinement: needs an AppArmor kernel; runs in CI) |
| gitleaks 8.30.0 (`dir` scan of the branch) | No leaks found |
| pip-audit | **Not run here** (the sandbox cannot resolve packages for it); runtime requirements are unchanged from PR #2; CI runs it |
| AppArmor under enforcement, hadolint, SBOM and licence check, image scan, aarch64 | **Not run here**; CI only |

## Measurements (amd64 container, stand-in base — not Pi validation)

| Measurement | Integration off | Integration on |
|---|---|---|
| Idle memory, RSS + swap of all app processes | 69.2 MiB | **71.3 MiB** |
| CPU over 120 s, idle, API polled every 30 s | 0.158 % of one core | 0.208 % of one core |
| Announce flood (L2, 256 MB limit, no swap, transport on) | Peak 70.4 MiB, no OOM kill | — |

## Defects found during development

| Finding | How found | Fix |
|---|---|---|
| A state change (for example needs-attention) reached the API only at the next 5 s publish | Integration test | Publish immediately on every state transition |
| `int()` of a NaN or infinite counter would crash the collector | Property-based test | Non-finite values are treated as unavailable |
| Root in the container cannot read the service user's `/proc/<pid>/environ` (no `CAP_SYS_PTRACE`), so a naive check failed | Container test | The test reads it as the service user (correct behaviour, not a defect in the app) |
| HA 2026.10 deprecates `DeviceInfo.via_device` | Strict mypy against HA's types | Peers are entities of the node device, not separate devices |
| The RNS version lookup scanned site-packages on every snapshot | Review | Looked up once |

## Not yet verified

- Against the real Supervisor and Home Assistant on the reference Pi (OB-2, OB-9, OB-10, OB-13). This must wait until the v0.1 soak has finished.
- aarch64, AppArmor enforcement with the new listener, and the real HA base image: CI (OB-14).
