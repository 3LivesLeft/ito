# ADR 0022: One standard image, LXMF messaging behind an option

**Status:** Accepted (maintainer, 20 November 2026; M4 decision D-M4-8). **Supersedes:** the M4
plan's WP5 ("messaging absent from production images"). **Related:** ADR 0008 (messaging
process), ADR 0009 (messaging identity), ADR 0014 (engine contract), ADR 0018 (isolation by user).

## Context

M4 built the LXMF messaging engine as a separate process and user, and shipped it only in a
development image (`messaging-dev`) while the production image excluded every part of it. That
kept production small and unchanged, but it meant two images, a dual-image release and test set-up,
and no way for a user to try messaging with a normal installation.

## Decision

1. **One image for everyone.** The standard image carries the Reticulum gateway and the messaging
   engine, LXMF and the engine's s6 service, users and AppArmor rule. There is no development
   image and no build target to choose.
2. **Off by default, one checkbox.** The app option `messaging_enabled` (*Enable LXMF messaging*)
   is `false` on every fresh install and on upgrade. While it is off nothing of messaging runs:
   the root init step creates no messaging folder or data, the engine's service stays down,
   Reticulum does not share its instance, and the core builds no engine supervisor.
3. **On after a restart.** When the user ticks it and restarts the app, the core writes the
   engine's settings from the validated options and starts the engine once Reticulum is up. The
   messaging identity and queue are created on the first start and kept when messaging is
   switched off again. No live reload.
4. **Configuration through the supported mechanism only.** Contacts, "accept messages from
   anyone", the confirmation reply, an optional display name and an optional propagation node are
   app options, validated by the core. There is no settings file for users to edit.
5. **The engine's least privilege is unchanged.** The engine never reads `options.json` (it holds
   peer passphrases); the core writes only the engine's settings to
   `/run/meshbeacon-messaging/config/settings.json` (owner the core, group `mb-msg`, 0640, in a
   0750 folder), which the engine can read and not change, and which Reticulum's user cannot reach.
   The engine still has no node RPC key (IS-3a), its own user, identity and socket with peer checks
   both ways, and its failures never touch Reticulum (MS-15).
6. **The smallest usable interface (M4).** So that messaging can be tested with Sideband or
   Ratspeak without Home Assistant messaging (M5), the core counts arrivals, can answer each
   contact's message with a fixed confirmation (option, on by default), acknowledges arrivals
   (which deletes them) and reports state, the engine's own address and counts in the status API.
   The core never logs, stores or forwards message content. The dashboard shows the state, the
   address (copyable; kept out of Home Assistant's history) and how to connect an app.

## Consequences

- **Security defaults are not weakened.** Messaging stays opt-in; with it off the running app is
  as before (MS-1, measured against v0.2). The added attack surface while off is code and two
  users present in the image but never executed; the production AppArmor profile gains one rule
  (`/run/meshbeacon-messaging/{,**} rw,`), validated under enforcement in CI since M4 WP6.
- **The image is larger** by LXMF (pure Python, about 1 MB); idle memory is unchanged while
  messaging is off.
- **Release verification flips:** instead of refusing any layer holding the engine, it requires
  the engine, LXMF, the service and the service's `down` file in every candidate.
- **WP5's exclusion evidence is superseded** (kept in the M4 results as history), replaced by
  positive tests: the engine is present, off by default, exactly one engine when on, toggling
  keeps both identities, and a v0.2 installation upgrades with messaging off.
- Hardware and device acceptance (MS-14, MS-18, the Pi half of MS-1, IS-4 on a VM) is unchanged
  and still outstanding.
