# Roadmap

Status: **Provisional.** Revised after Phase 0 research; every item is open to challenge.
Changes from the original brief are marked **Changed** with the reason.

## Phase 0 — Research and foundations (this phase)

Documentation only: research, architecture, threat model, testing strategy, ADR 0001.
**Exit:** maintainer review and approval; licence decision (Q-1); name decision (Q-3) or explicit
deferral.

## v0.1.0 — Foundation

- Installable Home Assistant app (formerly "add-on") for `aarch64` and `amd64`.
- Native RNS service (unmodified reference implementation, pinned), supervised child process.
- Persistent transport identity with enforced file permissions; refuses silent regeneration.
- Configurable outbound TCP client interfaces; **no default remote**.
- Optional transport mode (off by default).
- Optional TCP listener (off by default, explicit warning).
- Automatic start-up and recovery (back-off, circuit breaker, memory guard).
- Basic health monitoring (Supervisor `watchdog`, logs).
- `stage: experimental`.

**Changed:** "Configurable TCP interfaces" narrowed to *client* interfaces plus an opt-in
listener, because the target is behind CGNAT and listeners expose ports.

See the proposed [acceptance criteria](#v010-acceptance-criteria-proposed).

## v0.2.0 — Visibility

- HA custom integration (HACS), communicating with the app's local API.
- Entities: node health, per-interface status, RX/TX bytes, link counts, path-table size, RSS.
- Diagnostics download (redacted).
- Optional Lovelace dashboard example.

**Changed:** entities are delivered by a custom integration rather than by the app writing states,
to keep the app free of HA Core API permissions (feasibility §12).

## v0.3.0 — Messaging

- LXMF send/receive via a HA `notify` platform.
- Interop testing with Sideband, NomadNet, MeshChat and Ratspeak (Ratspeak uses a Rust stack;
  interop unverified — Q-13).
- Optional propagation node (opt-in, disk quota).

**Note:** "Encrypted Home Assistant notifications" — LXMF encrypts end-to-end between identities;
HA composes the plaintext. Documentation must say so.

## v0.4.0 — Privacy and reachability

- Optional I2P via a separate I2P router (SAM) and `I2PInterface`.
- Investigate public gateway hosting behind CGNAT (I2P, user's tailnet, or user's VPS), with RNS
  native protections (filters, stamps, blackholes).

**Changed:** Tailscale guidance (linking the user's own nodes over their tailnet) moves earlier, to
v0.1 documentation, because it needs no code — just a user-chosen peer address. Needs Q-8 tested.

## v0.5.0 — Off-grid

- RNode support via explicit device mapping; regional LoRa parameter validation.
- Hybrid internet + radio; internet-independent local communication.

**Note:** this is the first version that *optionally* needs additional hardware.

## v0.6.0 — Remote automation

- Authenticated, explicitly authorised remote commands over LXMF.
- Identity allowlists, command allowlists mapped to fixed HA actions, replay protection, rate
  limits, audit log (see [threat model §4](security/threat-model.md#4-later-versions-outline)).

**Challenge:** this is the highest-risk feature in the roadmap. Consider an external review of its
design *before* implementation, not only at v1.0.

## v1.0.0 — Stable

- External security audit; compatibility matrix; comprehensive documentation; standalone Docker
  image of the same core.

**Added:** a documented RNS-upgrade policy (how quickly MeshBeacon follows RNS releases, especially
security fixes), given the upstream mirror-only model (risk R-1).

---

## v0.1.0 acceptance criteria (proposed)

Functional

1. Installs from a repository URL on HA OS (aarch64 Pi 4B and amd64) and starts without errors.
2. With no interfaces configured, starts and reports `healthy`, making **no outbound
   connections** (verified by packet capture or container network policy in test).
3. With one TCP client interface to a user-specified peer, connects and shows the interface as up
   in logs/health; survives peer restart and reconnects automatically.
4. Transport mode can be enabled and disabled via options; default is disabled.
5. Transport identity persists across app restart, update, HA reboot and hot backup/restore (node
   identity hash unchanged).
6. If an identity existed and is now missing or corrupt, the app refuses to start with an
   actionable message unless the user sets an explicit regenerate option.
7. Killing the RNS child results in automatic restart within 30 s; repeated crashes trip the
   circuit breaker without restarting HA.

Security and privacy

8. `config.yaml`: no `host_network`, no `hassio_api`, no `homeassistant_api`, no `privileged`,
   no `full_access`, no `docker_api`, no published ports, AppArmor profile present.
9. Supervisor security rating of 8 (the maximum) with default options.
10. Identity, rendered config and tokens are `0600`; data directories `0700`.
11. No `AutoInterface`, discovery, auto-connect, `publish_ifac` or `location_cmd` in the rendered
    config.
12. No key material in logs at any log level MeshBeacon exposes.
13. Dependencies installed with hash pinning; base image pinned by digest; image signed; SBOM
    published.
14. CI runs lint, unit, isolated integration, container tests for both architectures, secret and
    vulnerability scanning — all green.

Resources

15. Idle RSS of the whole app ≤ 128 MB on aarch64 (measured RNS alone: ~55 MB on x86-64).
16. 72-hour soak on the Pi 4B with transport off shows no monotonic memory growth.

Documentation and provenance

17. `DOCS.md` explains: what the app does, privacy implications of each option, how to choose a
    peer, backups contain the private key, experimental status.
18. RNS licence notice and `THIRD_PARTY_NOTICES` shipped in the image.
19. AI assistance disclosed; every merged change reviewed by the named human maintainer.
