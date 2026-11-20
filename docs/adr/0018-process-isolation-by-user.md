# ADR 0018: Process isolation by Unix user, supervised by s6

- **Status:** **Accepted** (maintainer, 19 Nov 2026, D-M4-1). Implemented for the core and Reticulum
  in M4 WP1; the engine follows in WP3.
- **Date:** 19 November 2026
- **Implements:** the mandatory [process isolation gate](../roadmap.md#process-isolation-gate-mandatory)
  (IS-1 to IS-4). Amends [ADR 0008](0008-messaging-process.md) (who starts the messaging process).
- **Related:** [ADR 0005](0005-bounded-recovery.md), [ADR 0017](0017-independent-node-services.md), threat T72.

## Context

The core starts Reticulum as its own child and signals, memory-limits and log-filters it directly.
That is why both run as one user: an unprivileged process cannot signal another user's process.
The gate requires separate users for the core, Reticulum, LXMF and each community service, with
least-privilege credentials, storage and IPC, proven by adversarial tests.

## Options

| | A. s6 services, one per user, controlled by the core | B. A small root launcher | C. Keep one user |
|---|---|---|---|
| New root code | **None** (s6-supervise already runs as root) | A new privileged service and protocol | None |
| Memory | s6-supervise per service (well under 1 MiB) | + one Python process (about 10 MiB), always | None |
| Core's restart policy, memory watchdog, log redaction, status line | Kept, over FIFOs and `s6-svc` | Kept, over passed descriptors | Kept |
| Meets the gate | Yes | Yes | **No** |

**[Verified]** s6-overlay 3.2.3.2 (pinned) ships `s6-svc`, `s6-svstat`, `s6-svwait` and
`s6-svperms` (s6 2.15.1.0).

## Decision (proposed)

**A.**

1. **Users.** `meshbeacon` (9100) is the management core, as today, so its data keeps its owner.
   Reticulum and its prepare step run as `mb-rns` (9101); the LXMF engine runs as `mb-lxmf` (9102).
   Each has its own group. No two services share a user or a group, and none is root.
2. **Supervision.** Reticulum (`reticulum`), the prepare step (`rns-prepare`, one-shot) and the
   engine (`messaging`) are s6 services that start **down**. Their run scripts drop to their own
   user with `s6-setuidgid` and use fixed command lines only. The root init step grants the core's
   group control of exactly these services (`s6-svperms`). The core keeps its decisions: it starts an
   attempt (`s6-svc -o`), stops or kills (`-d`, `-k`), reads the state (`s6-svstat`), and applies the
   bounded restart policy of ADR 0005 itself.
3. **Output and status.** Each service writes stdout and its status line to FIFOs in
   `/run/meshbeacon/<service>/`, created by the root init step. They are writable by the service
   user and readable only by the core's group. The core reads and redacts them exactly as now.
4. **Memory watchdog.** The core reads `VmRSS` and `VmSwap` from `/proc/<pid>/status`, which is
   world-readable, and kills through `s6-svc -k`.
5. **Storage.** `/data/reticulum` belongs to `mb-rns`, `/data/messaging` to `mb-lxmf` and
   `/data/meshbeacon` to the core, each 0700. The init step sets ownership at every start. Identity
   files are never rewritten, only re-owned. An older image's init step re-owns them back, so a
   downgrade keeps the identity.
6. **IPC.** The engine's contract channel (ADR 0014) is a Unix socket owned by `mb-lxmf`, group
   `meshbeacon`, mode 0660, in a 0750 folder. Each end checks the other's user ID (`SO_PEERCRED`).
   The engine needs no RNS RPC key: it is a shared-instance client only (verified in M4 with
   RNS 1.6.0 and LXMF 1.3.0; see point 11 and IS-3a).
7. **AppArmor.** There is still one profile (all services run `python3`), and no capability is
   added. **As implemented:** `/data/<service>/` cannot become `owner` rules, because the root init
   step must re-own files it does not own at every start, and a single profile cannot tell root
   from the services. Cross-service file isolation therefore rests on separate users and 0700
   folders, proven by the isolation test (IS-3, IS-4). The channels in `/run/meshbeacon-io/` are
   allowed by path; their modes keep Reticulum out.
8. **Credentials.** The discovery credentials stay with the core (non-dumpable; T72). The messaging
   identity and queue are readable only by `mb-lxmf`.

9. **Start-up (as implemented).** `S6_CMD_WAIT_FOR_SERVICES=0`: otherwise s6-overlay waits, with
   no time limit, for every service to be up, and the services that start down would block
   start-up and shutdown for ever. It only gates a container `CMD`, which MeshBeacon does not have.
10. **The container environment (as implemented).** s6-overlay keeps a copy of the container's
    environment, the Supervisor token included, in `/run/s6/container_environment`, readable by every
    user. The root init step makes it root's alone (0700, files 0600). The isolation and credential
    probes check it.
11. **The messaging engine (as implemented, M4).** Only in the `messaging-dev` image target; the
    production target has no `messaging` service, no `mb-lxmf` user and no engine (WP5).
    - The core starts the `messaging` service once Reticulum has reported its first status, checks
      its health every 30 s over the contract socket (three missed answers count as a hang), and
      restarts it with back-off (10 s to 5 min). After five failures in 30 minutes messaging pauses
      until the app restarts. Reticulum and the status API are never touched (MS-15).
    - **Socket path, changed from point 6:** `/run/meshbeacon-messaging/engine.sock`, in a folder
      `mb-lxmf:meshbeacon` 2750 (the socket inherits the core's group), socket 0660. Point 6's
      folder inside `/run/meshbeacon-io/` would have needed `mb-lxmf` in the core's group, because
      that folder is root:meshbeacon 0750. The engine's output still goes through a FIFO in
      `/run/meshbeacon-io/messaging/`, opened by root in the run script, and through the core's
      redaction.
    - The `s6-svperms` step now grants the core control of every service that starts down (each
      service folder with a `down` file), so it names no messaging service in production.
    - At a container stop s6-overlay stops every service at once, so the engine is not guaranteed
      to stop before Reticulum then. It exits cleanly on SIGTERM either way (tested); the core stops
      it first only when the core itself stops.

## Consequences

- The core no longer holds Reticulum's stdout pipe or PID as a child. `PR_SET_PDEATHSIG` is
  replaced by s6: the services are stopped when the core stops (its finish script), and the
  container stops if the core crashes (ADR 0005).
- More moving parts: FIFOs, service directories and permission grants. They are tested in the
  container, under AppArmor, and against a deliberately weakened build (IS-4).
- **Fallback:** if a spike shows that s6 control or the FIFOs cannot meet ADR 0005's timings, option
  B returns for review. It is not adopted silently.

## Review triggers

Any new service, any new IPC channel, any credential shared between services, or any service that
needs root.
