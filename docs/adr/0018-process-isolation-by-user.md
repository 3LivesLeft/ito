# ADR 0018: Process isolation by Unix user, supervised by s6

- **Status:** **Proposed** (for the maintainer's approval with the [M4 plan](../plans/m4-lxmf-engine.md)).
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
   The engine needs no RNS RPC key: it is a shared-instance client only.
7. **AppArmor.** There is still one profile (all services run `python3`). File rules for
   `/data/<service>/` become `owner` rules, so AppArmor refuses cross-service file access as well as
   the file modes do. No capability is added.
8. **Credentials.** The discovery credentials stay with the core (non-dumpable; T72). The messaging
   identity and queue are readable only by `mb-lxmf`.

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
