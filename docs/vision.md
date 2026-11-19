<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../branding/png/logo-horizontal-dark.png">
  <img src="../branding/png/logo-horizontal-light.png" alt="MeshBeacon" height="48">
</picture>

# Vision

> **Decentralised connectivity for your home.**

Status: revised 19 November 2026 to record the agreed long-term direction. The tagline is
unchanged (ADR 0003); whether it still fits is [Open] Q-41.

## The problem

Home Assistant runs the home, but almost every way of reaching it from outside — or of receiving
alerts from it — depends on the internet, and often on a third-party cloud. When the broadband
goes down, the mobile network is congested, or a cloud service changes its terms, the household
loses its link to its own home.

[Reticulum](https://github.com/markqvist/Reticulum) is a mature, cryptography-based networking
stack designed to work over almost any medium, from the internet to long-range radio, with no
central authority. It already powers messaging apps such as Sideband and a growing mesh of
community nodes. But running it today requires comfort with configuration files, command lines
and networking concepts that most Home Assistant users do not have.

## What MeshBeacon is

MeshBeacon is a **free, open-source, privacy-first Home Assistant app** that runs the Reticulum
reference implementation for you and connects it to Home Assistant — safely, with sensible
defaults, and without extra hardware to begin with.

Over time it aims to let a household:

- run a well-behaved Reticulum node on the Home Assistant machine it already has;
- see the node's health and network status as ordinary Home Assistant entities;
- receive end-to-end-encrypted notifications from Home Assistant in any Reticulum messaging app;
- keep communicating locally, and over radio, when the internet is unavailable;
- eventually, monitor and control the home off-grid — with strong, explicit authorisation.

## Long-term direction

Beyond the household, MeshBeacon is evolving into a free, open-source, privacy-first,
decentralised **community network that can continue operating without internet connectivity**.
The goal is to let communities host and discover information, communicate and share resources
over Reticulum, including compatible LoRa radio links: private messaging, Nomad Network-compatible
pages, bulletin boards and offline libraries, short voice messages, and resilient, replicated
infrastructure.

Home Assistant remains a **first-class deployment and management interface**, but the underlying
community services must not depend on Home Assistant to function. The milestones that lead there
are in the [roadmap](roadmap.md#long-term-direction-proposed); from v0.4 onwards they are
proposals, not commitments.

### Architectural principles for the long-term direction

These add to the principles below; where they overlap, the stricter reading applies.

1. **Offline-first.** Public internet connectivity is optional, never required.
2. **Interoperable** with existing Reticulum and LXMF clients, using the same protocols.
3. **LoRa-aware.** Designs respect strict bandwidth, airtime and regulatory constraints.
4. **Public community services are isolated** from Home Assistant's private APIs and data.
5. **Secure-by-default publishing**: access controls, rate limits, storage quotas and abuse
   protections.
6. **No central cloud service, subscription or mandatory account.**
7. **Modular**, so that it can eventually run standalone on a Raspberry Pi or other Linux system.
8. **Compatible with existing MeshBeacon installations and identities.**

v0.3 decisions that could constrain these are reviewed in the
[forward-compatibility review](research/long-term-direction.md).

## What MeshBeacon is not

- **Not a Reticulum implementation.** MeshBeacon uses the reference implementation unchanged. It
  does not reimplement, fork or "improve" the protocol.
- **Not a product.** No commercialisation, no paid tier, no telemetry, no analytics, no adverts.
  Its own code is open source under Apache-2.0.
- **Not a cloud service.** Nothing depends on servers run by the MeshBeacon project, and nothing
  depends on any one public peer operator.
- **Not affiliated** with the unrelated MeshBeacon disaster-response project (meshbeacon.org).
- **Not finished.** MeshBeacon is experimental until v1.0 and should be treated that way.

## Principles

1. **Easy to use.** A non-technical Home Assistant user can install MeshBeacon and be connected to
   Reticulum within five minutes, without editing a file or understanding networking. Safe
   defaults and a few plainly explained choices beat many options. See
   [first-run UX](ux/first-run.md).
2. **Works out of the box (permanent; maintainer, 18 Nov 2026).** Everything a first-time user
   needs comes with the standard app installation:
   - No terminal, no file copying, no third-party installer and no manual dashboard
     configuration. **Amended (maintainer, 19 Nov 2026, decision D1):** MeshBeacon's interface,
     with its sidebar entry, arrives through Home Assistant's own app store and Marketplace in at
     most two guided steps ([ADR 0015](adr/0015-distribution-and-updates.md)). A one-step install
     remains the goal (Ingress after upstream hardening, or an integration shipped with Home
     Assistant), but never at the cost of security.
   - A first-time user can install, configure and start MeshBeacon within **five minutes**,
     without touching a terminal or editing YAML.
   - The Home Assistant integration remains an **optional enhancement**, for entities, custom
     dashboards, long-term statistics and automations. Nothing essential depends on it.
   - This never justifies weakening security or privacy (principles 5 and 6). When the two
     conflict, the safe design wins and the usability gap is recorded as a defect to solve.
   - It never justifies duplicating monitoring logic or adding avoidable resource use
     (principle 10).
3. **Consistent branding (permanent; maintainer, 18 Nov 2026).** MeshBeacon looks and reads the
   same everywhere: app store, sidebar, interface, integration, README and documentation. It uses
   one name, one mark, one palette and one type system, defined in [branding](branding.md). The
   brand complements Home Assistant and follows the user's theme. It never adds external fonts,
   CDNs, tracking, permissions or resource use, and never relies on colour alone.
4. **Free for everyone, forever.**
5. **Privacy by default.** Nothing is published, discovered or connected without the user's
   explicit choice.
6. **Security by default.** Least privilege, no privileged containers, no unnecessary Home
   Assistant permissions, no public ports by default.
7. **Reuse upstream.** Build on RNS and LXMF through their public interfaces; never copy or patch
   them.
8. **Native interoperability.** Talk to the wider ecosystem (Sideband, Ratspeak, NomadNet,
   MeshChat) because it is the same protocol — not through bridges or translations.
9. **Good network citizenship.** Be a considerate neighbour on shared networks and shared radio
   spectrum.
10. **Light on resources.** The Home Assistant host comes first. MeshBeacon must run comfortably on
   lower-memory devices, not just on well-equipped ones: the idle target is 128 MB or less.
11. **Maintainable, testable and portable.** A small core that runs with or without Home
   Assistant, tested against real, isolated Reticulum networks.
12. **Honest.** Clear about what works, what does not, what is experimental, and how the project
   is made — including the use of AI assistance.
13. **British English** throughout documentation.

## Who it is for

- Home Assistant users who want resilient alerts and access without relying on cloud services.
- Households in areas with unreliable connectivity, or preparing for outages.
- Existing Reticulum users who already run Home Assistant and want the two to work together.
- Later: communities that want local messaging, information and services that keep working when
  the internet does not.

## Measures of success

- An ordinary Home Assistant user can install MeshBeacon and have a connected, private node in
  **five minutes or less**, without editing a configuration file or opening a terminal, and can
  see it working in MeshBeacon's own interface, measured with real users.
- MeshBeacon never degrades the stability of the Home Assistant instance it runs on.
- Reticulum community members regard MeshBeacon as a good citizen of the network.
