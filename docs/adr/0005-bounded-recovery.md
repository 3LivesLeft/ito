# ADR 0005: Bounded recovery that cannot loop with the Supervisor watchdog

- **Status:** Accepted
- **Date:** 18 November 2026
- **Evidence:** [Architecture §4.2, §4.4, §4.5](../architecture.md#42-process-supervision-and-bounded-recovery)

## Context

MeshBeacon restarts its RNS child after failures, and the Home Assistant Supervisor can restart
the whole app through its watchdog. Supervisor 2026.11.0 (verified) restarts the app after two
failed health checks with no limit on the number of restarts, and restarts failed containers at
up to 10 per 30 minutes, again without a final stop. If the two mechanisms are combined naively —
for example by reporting "circuit breaker open" as unhealthy — a persistent fault produces an
endless restart loop that cannot fix the problem and wears the SSD.

## Decision

1. Failures are classified as **deterministic** (stop immediately, `needs_attention`) or
   **transient** (bounded back-off and circuit breaker; give up after 3 openings without a stable
   10-minute run).
2. The health endpoint fails **only when the core is unresponsive**. Connectivity problems,
   `restarting` and `needs_attention` all report healthy.
3. A persisted **start history** puts the core into **safe mode** (RNS not started) after 5 starts
   in 30 minutes without a stable run, whatever caused them.
4. If the core process exits, s6 stops the container rather than looping internally.

## Consequences

- Every restart path has a bound; the worst case ends in a clearly explained, stable, healthy
  state that waits for the user.
- A real fault leaves the app "running" in Home Assistant while not running RNS; the log message,
  and from v0.2 a repair issue, must make that obvious.
