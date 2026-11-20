# M4 acceptance on the reference Raspberry Pi: MS-1 and MS-18

**Status: prepared, not run.** Nothing has been installed on, or changed on, the Pi. Every step
that changes the installation is marked **(approval)** and needs the maintainer's explicit
go-ahead first. Record results in [M4 results](m4-results.md) with no household identifiers
(CLAUDE.md rule 15): no addresses, hostnames, URLs or identity hashes.

## What is measured, and against what

| ID | Criterion (roadmap) | Measured here as |
|---|---|---|
| MS-1 | Messaging off: no messaging process, no `/data/messaging/` writes, no new endpoints, memory and CPU unchanged from v0.2 (±2 MiB) | M4 **production** image against the **v0.2** production image, both idle with default options, on the same Pi |
| MS-18 | Messaging on: idle ≤ +40 MiB (app ≤ 160 MiB) and ≤ 0.5 % CPU added; stamp at the recipient's cost ≤ 30 s or a clear failure | M4 **messaging-dev** image against the M4 production image, both idle, on the same Pi; stamp time (Q-41) separately |

**Memory is a runtime reading, never an image size.** The primary figure is the Supervisor's
memory figure for the app's container. [Verified] Supervisor 2026.11.0, `supervisor/docker/stats.py`
lines 22–33, computes it as cgroup usage minus inactive file cache. It therefore counts every
process in the app plus its active page cache, so it is the **conservative** reading. The app's
own `Status:` log line adds the core's and Reticulum's RSS + swap, the same definition the
container tests use. So the engine's share of any difference can be separated from the rest.
CPU from the Supervisor is a share of the **whole machine** (same file, line ~85: not multiplied
by the number of CPUs). On a 4-core Pi, 0.5 % on the app page is 2 % of one core. See decision P-2.

## Decisions needed before the run

| ID | Decision | Recommendation |
|---|---|---|
| **P-1** | The plan (D-M4-7) names a **spare** Pi. This procedure uses the **live** reference Pi instead, without disturbing the installed app | Accept, with the controls below. The spare Pi stays the fallback if any control cannot be met |
| **P-2** | Basis for "0.5 % CPU" (MS-18) | **One core** (the stricter reading: 0.5 % of a core = 0.125 % on the app page). Both are reported |
| **P-3** | Tolerance for "CPU unchanged" (MS-1), which the roadmap does not quantify | ≤ 0.1 percentage points of one core between the means |
| **P-4** | How to measure stamp time (Q-41) on the Pi, which needs a Python with LXMF on the Pi | See [step D](#d-stamp-time-q-41-approval): option D1 if the SSH app has Python 3.13, otherwise D3 |

## Safety controls

| Risk to the live installation | Control |
|---|---|
| A test copy replaces or updates the installed MeshBeacon app (`local_meshbeacon`, folder `/addons/meshbeacon`) | Each test app has its **own folder and slug** (`meshbeacon_v02`, `meshbeacon_m4p`, `meshbeacon_m4d`), so the Supervisor installs it as a separate app. `tools/acceptance/pi_test_apps.py` refuses a source whose slug is not `meshbeacon`, and tests check that no output keeps it |
| Its identity or data are overwritten | A separate slug means a separate `/data`. The installed app's data, identity and options are never read or written. Test apps create throwaway identities in their own data, deleted at uninstall |
| A test app joins the live Reticulum network | Test apps run with **default options: no peers, transport off**. MeshBeacon opens no interface but configured peers (no auto, LAN or listening interface), and the app has no host network and no published ports. Rule 6 holds |
| It talks to Home Assistant | The integration option stays **off** (default), so no discovery message is posted and Home Assistant sees nothing new |
| It starts by itself after a reboot | `boot: manual` in every test app |
| More than one runs at once, or the wrong one is stopped | `pi_measure.sh` starts and stops only `local_meshbeacon_<v02\|m4p\|m4d>`, refuses to start while another test app runs, and only *reads* the live app (tests check that no other start or stop exists) |
| Security weakened to make it work | The SSH app's **protection mode stays on** (no Docker access), as the install guide requires. The production AppArmor profile is unchanged; the dev test app uses exactly the profile CI uses for the dev image (one added rule, `/run/meshbeacon-messaging/{,**} rw,`; checked identical) |
| Load on Home Assistant | Builds (a few minutes each) and stamp benchmarks run at a quiet time; stamp work runs at `nice 19` with a hard timeout. RNS 1.6.0 spreads high-cost stamps over several processes (`RNS/Stamps.py`, line 274, `job_linux`), so up to all four cores at the lowest priority |
| Something goes wrong anyway | Full backup first (A2); rollback in [section F](#f-rollback) |

**What the test apps are.** `pi_test_apps.py` copies `meshbeacon/` and changes only `slug`,
`name`, `description` and `boot` in `config.yaml`. For `meshbeacon_m4d` only, it also drops the
Dockerfile's last line (`FROM app AS production`), so the Supervisor, which builds the last stage,
builds the approved `messaging-dev` stage, and it adds CI's dev AppArmor rule. Evidence that these
are the approved images (local, amd64, from `feature/m4-final-acceptance`):

| Check | Result |
|---|---|
| Diff of each generated folder against its source | Only the lines listed above |
| Generated dev profile against CI's derived dev profile | Identical (apart from the profile name, which the Supervisor sets) |
| Images built from the generated folders the way the Supervisor builds them (no `--target`) against the approved images | Same file list; same content hash over the core code, services and accounts (`m4p` = production, `m4d` = messaging-dev) |
| Full container suite on the generated images | **32 passed, 1 skipped** (AppArmor enforcement: CI), as on the approved images |

## A. Pre-flight (read-only)

| # | Step | Pass condition | Result |
|---|---|---|---|
| A1 | Copy `tools/acceptance/pi_preflight.sh` and `pi_measure.sh` into the Samba share's `share` folder, as `meshbeacon-m4/` (on the Pi: `/share/meshbeacon-m4/`) | Files present | |
| A2 | Take a **full backup** (Settings → System → Backups → Backup now) | Backup listed | |
| A3 | In the **Advanced SSH & Web Terminal** (protection mode **on**): `sh /share/meshbeacon-m4/pi_preflight.sh`. It changes nothing and prints no addresses or options; read it before sharing | `aarch64`, 4 CPUs; RAM, swap and free storage recorded; HA Core, OS and Supervisor versions recorded, healthy and supported; `local_meshbeacon` started; the three test slugs **free**; docker **not reachable** | |
| A4 | Note the live app's uptime: its Log tab's first `MeshBeacon … starting` line and time | Recorded (used in F3 to show it was never restarted) | |

## B. Install the test apps (approval)

| # | Step | Pass condition | Result |
|---|---|---|---|
| B1 | On a computer, from a checkout of this branch: `git archive main meshbeacon \| tar -x -C <empty-dir>`, then `python3 tools/acceptance/pi_test_apps.py <out-dir> --v02 <empty-dir>/meshbeacon` | Three folders, each printed with its own slug | |
| B2 | Copy the three folders from `<out-dir>` into the Samba share's `addons` (or `local_apps`) folder, **beside** `meshbeacon`, which is not touched | `/addons/meshbeacon_v02/config.yaml` etc. present; `/addons/meshbeacon` unchanged | |
| B3 | App store → ⋮ → **Check for updates** | Three new local apps, named "MeshBeacon test: …". The installed MeshBeacon shows **no** update | |
| B4 | Install each test app in turn (the Pi builds it: several minutes each). Do **not** start them, and leave Watchdog off | Installed; record the build time and the security rating on each Info tab | |

## C. Runtime measurements (approval)

Six runs, one test app at a time, alternating so that drift in the rest of the system averages out:
`v02 1`, `m4p 1`, `m4d 1`, `v02 2`, `m4p 2`, `m4d 2`. Each run lasts 40 minutes (10 settling,
30 sampling every 30 s), about 4 hours in all. In the terminal:

```sh
cd /share/meshbeacon-m4
nohup sh pi_measure.sh v02 1 > v02-run1.out 2>&1 &   # then wait for "stopping" in v02-run1.out
```

| # | Step | Pass condition | Result |
|---|---|---|---|
| C1 | The six runs, in that order | Each `.out` ends with "N samples …" and "stopping"; each `.csv` has about 60 samples | |
| C2 | During an `m4d` run, its Log tab | One `meshbeacon-messaging: started` line and no engine restart; `Status:` lines present | |
| C3 | After each `m4d` run: `ha host logs -t kernel -n 2000 \| grep -i 'apparmor="DENIED"' \| grep local_meshbeacon_m4d`, and the same with `-t audit` | No denials (supplementary evidence for IS-4: the Supervisor-loaded dev profile on real hardware) | |
| C4 | During an `m4p` run, the app page and log (MS-1) | No network ports listed; no messaging lines in the log | |

## D. Stamp time, Q-41 (approval)

`tools/acceptance/stamp_benchmark.py` times LXMF's public `LXMF.LXStamper.generate_stamp` at
costs 8 to 16 (5 trials each, 120 s timeout per trial, at `nice -n 19`). MS-18 passes for a cost
when a stamp is ready in ≤ 30 s or the timeout gives a clear failure. Which cost matters is
recorded in MS-14 (Q-42: what Sideband and Ratspeak ask for).

| Option | How | Trade-off |
|---|---|---|
| **D1** | In the SSH app, if A3 shows Python 3.13 and pip: a temporary virtual environment in `/tmp` with LXMF 1.3.0 and RNS 1.6.0 installed **by hash** from the repository's requirements files, then the benchmark | Same CPU, same LXMF; not inside the app container. Protection mode stays on. Gone when the SSH app restarts |
| D2 | Inside `local_meshbeacon_m4d` with `docker exec` | Exactly the app's environment, but it needs the SSH app's **protection mode off**, which exposes every app's data, the live identity included, to that app for the duration. **Not recommended** |
| **D3** | Defer to MS-14: time the engine's own outbound stamp to a recipient that asks for one | The real engine, but only at the costs the MS-14 clients ask for |

## E. Analysis (on a computer)

Copy `/share/meshbeacon-m4/` off the Pi, then:

```sh
python3 tools/acceptance/pi_summary.py <folder> --cpu-basis core --cpu-unchanged 0.1
```

It prints one line per run and the verdicts: MS-1 memory and CPU, MS-18 memory (added, app total
and the engine's share) and CPU, and whether the live app was `started` in every sample.
**A failed MS-18 memory criterion is not overridden here:** D-M4-7 then returns the plan for
review (ADR 0008: revisit the in-process option, or lower the engine's memory).

## F. Rollback

| # | Step | Pass condition | Result |
|---|---|---|---|
| F1 | Stop and **Uninstall** each test app (this deletes only that test app's data and throwaway identity) | Gone from Settings → Apps | |
| F2 | Delete `meshbeacon_v02`, `meshbeacon_m4p` and `meshbeacon_m4d` from the local apps folder; App store → ⋮ → Check for updates. Keep `/addons/meshbeacon` | Only the live app remains | |
| F3 | Live app: still started, still 0.2.0, the same first `starting` line as in A4 (never restarted), peers connected as before | As before | |
| F4 | After copying the results off, delete `/share/meshbeacon-m4/` (and the D1 virtual environment, if used) | Removed | |
| F5 | Only if anything else changed: restore the MeshBeacon app, or the whole system, from the A2 backup | — | |

## Notes

- **Question numbers.** `docs/research/v0.3-messaging.md` and `docs/research/feasibility.md` both
  number open questions Q-40 to Q-44, with different meanings. Here, as in the M4 plan, Q-40 to Q-46
  are the messaging register's (Q-41: LXStamper time on a Pi 4 at costs 8–16).
- **Network.** The reference environment records Wi-Fi as the Pi's default interface (Q-31). The
  maintainer now reports Ethernet; the preflight records the host facts, not the interface.
- **Not on the Pi.** MS-14 (on devices, isolated network) and IS-4's VM run (RG-13) are separate.
