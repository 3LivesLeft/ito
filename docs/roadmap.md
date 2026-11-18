# Roadmap

Status: **Provisional — revised after independent review.** Every item remains open to challenge.

## Phase 0 — Research and foundations (this phase)

Documentation only. **Exit:** maintainer approval of PR #1, including the review amendments
(licence Apache-2.0, name retained with conditions, presets policy, security clarifications,
narrowed v0.1.0 scope).

## v0.1.0 — A reliable, installable Reticulum node

**Deliberately small.** The goal is one thing done well: a Reticulum node that installs in minutes,
stays up, keeps its identity and explains itself in plain language.

In scope:

1. Installable Home Assistant app (formerly add-on) for `aarch64` and `amd64`, `stage:
   experimental`.
2. Unmodified RNS (pinned) as a supervised child process running as a non-root user.
3. **Simple configuration:** optional verified public peer presets (none selected by default) and
   custom outbound TCP peers (host, port, optional network name and passphrase); log detail.
4. **Persistent identity:** atomic creation, validation before every start, verified backup copy,
   no silent replacement, explicit regenerate option.
5. **Optional transport mode**, off by default, explained in plain language.
6. **Basic diagnostics:** startup report and periodic status lines in the app log; process-health
   endpoint for the Supervisor watchdog; separate connectivity status messages, including the
   isolated-node warning.
7. Resource guards: memory, CPU priority, storage, log rate.

Explicitly **out of scope** for v0.1.0 (moved or deferred):

| Item | Where it went | Why |
|---|---|---|
| TCP listener (inbound) | Later, if requested | Exposes a port; not useful behind CGNAT; complicates UX |
| HA entities, dashboards | v0.2 | Needs the integration and local API |
| Identity import from file | v0.2 | Needs an extra file-transfer path and permissions |
| LXMF, notifications, propagation | v0.3 | |
| I2P | v0.4 | |
| RNode / LoRa | v0.5 | |
| Remote automation | v0.6 | |
| Raw RNS configuration | Not planned | Would bypass validation and privacy defaults |

## v0.2.0 — Visibility

- HA custom integration (HACS) with a token-authenticated local API.
- Entities: process health, connectivity state, per-peer status, RX/TX bytes, memory.
- Repair issues for "isolated node", "no peers reachable", "identity problem".
- Redacted diagnostics download; identity import.

## v0.3.0 — Messaging

- LXMF send/receive; HA `notify` platform (HA composes plaintext; LXMF encrypts end to end — must
  be documented).
- Interoperability testing with Sideband, NomadNet, MeshChat and Ratspeak.
- Optional propagation node with disk quota.

## v0.4.0 — Privacy and reachability

- Optional I2P via a separate router; investigate public gateway hosting behind CGNAT.
- Tailscale guidance (no code needed) is documented from v0.1 onwards once tested (feasibility
  Q-8).

## v0.5.0 — Off-grid

RNode support with explicit device mapping and regional parameter validation. First version that
*optionally* uses extra hardware.

## v0.6.0 — Remote automation

Authenticated, allow-listed remote commands with replay protection — external design review
**before** implementation.

## v1.0.0 — Stable

External security audit, compatibility matrix, full documentation, standalone Docker image, and a
published RNS-upgrade policy.

---

## v0.1.0 acceptance criteria (revised)

### Install and ease of use

1. Installs from a repository URL on HA OS on a Raspberry Pi 4B (aarch64) and on amd64, and
   starts without errors.
2. **Timed first-run test:** at least three people new to Reticulum reach a connected node on a
   fresh install with a median time of **≤ 5 minutes** and nobody over 10 minutes, using only the
   UI and `DOCS.md` ([first-run UX §7](ux/first-run.md#7-measuring-ease-of-use)).
3. All options have plain-language labels and descriptions; transport mode and public peers
   include the agreed explanations.

### Behaviour

4. With no peers configured, the app makes **no outbound connections** (verified by packet capture
   or a network policy in test) and logs the isolated-node warning, repeated at most every 6 hours.
5. With a custom peer, it connects, logs a plain "connected" message, and reconnects automatically
   after the peer restarts or the internet drops.
6. With presets: only presets that passed verification V1–V7 within 30 days of the release are
   offered, from at least two independent operators; otherwise none are offered.
7. Transport mode can be switched on and off; default off.
8. Internet loss changes the *connectivity* state only; the health endpoint stays healthy and the
   Supervisor does **not** restart the app.
9. Killing the RNS child causes automatic restart with back-off; repeated failures open the circuit
   breaker without restarting Home Assistant.

### Identity

10. The stored identity persists across restart, update, HA reboot and hot backup/restore
    (identity hash unchanged).
11. A corrupt or truncated identity is never replaced silently: the app restores from its verified
    backup copy if valid, otherwise refuses to start with the identity-problem message.
12. Power cut during first start (simulated by killing init mid-write) never leaves a partially
    written identity in place.

### Security

13. `config.yaml` requests no `host_network`, `hassio_api`, `homeassistant_api`, `auth_api`,
    `privileged`, `full_access`, `docker_api`, devices or published ports; a custom AppArmor
    profile is present. The Supervisor security rating is **8**, recorded as a target met — not as
    evidence of security.
14. The core and RNS run as the non-root `meshbeacon` user; the root init step does only the
    documented actions.
15. Identity, rendered config and state files are `0600`; directories `0700`.
16. The rendered RNS config never contains `AutoInterface`, discovery, auto-connect,
    `publish_ifac` or `location_cmd`.
17. The hostile-input suite passes: no user input can add, remove or rename sections or keys, or
    trigger interpolation, in the rendered config.
18. No key material, RPC key or passphrase appears in logs at any offered log level.
19. Private vulnerability reporting is enabled on the repository.

### Resources

20. Idle memory of the whole app ≤ 128 MB on aarch64.
21. 72-hour soak on the Pi 4B (transport off, then on) shows no monotonic memory growth, bounded
    `/data` growth and bounded log volume.
22. Under a local announce flood in test, logs remain rate-limited and HA stays responsive.

### Supply chain and licensing

23. Dependencies hash-pinned; base image digest-pinned; image Cosign-signed; SBOM published.
24. `THIRD_PARTY_NOTICES` (including the full Reticulum License text) and the GPL source bundle are
    published with the image (licensing O1–O7).
25. CI green: lint, unit, isolated integration, container tests on both architectures, secret
    scanning, vulnerability scanning, licence allow-list.

### Documentation and provenance

26. `DOCS.md` covers: what the app does, privacy of public peers, transport mode, backups contain
    the private key, how to restore, experimental status, Reticulum License conditions.
27. AI assistance disclosed; every merged change reviewed by the named human maintainer.
