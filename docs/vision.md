# Vision

> **Decentralised connectivity for your home.**

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
   - MeshBeacon's own interface, with a sidebar entry, is part of the app. It needs no separately
     installed custom integration, no HACS and no manual dashboard configuration.
   - A first-time user can install, configure and start MeshBeacon within **five minutes**,
     without touching a terminal or editing YAML.
   - The Home Assistant integration remains an **optional enhancement**, for entities, custom
     dashboards, long-term statistics and automations. Nothing essential depends on it.
   - This never justifies weakening security or privacy (principles 4 and 5). When the two
     conflict, the safe design wins and the usability gap is recorded as a defect to solve.
   - It never justifies duplicating monitoring logic or adding avoidable resource use
     (principle 9).
3. **Free for everyone, forever.**
4. **Privacy by default.** Nothing is published, discovered or connected without the user's
   explicit choice.
5. **Security by default.** Least privilege, no privileged containers, no unnecessary Home
   Assistant permissions, no public ports by default.
6. **Reuse upstream.** Build on RNS and LXMF through their public interfaces; never copy or patch
   them.
7. **Native interoperability.** Talk to the wider ecosystem (Sideband, Ratspeak, NomadNet,
   MeshChat) because it is the same protocol — not through bridges or translations.
8. **Good network citizenship.** Be a considerate neighbour on shared networks and shared radio
   spectrum.
9. **Light on resources.** The Home Assistant host comes first. MeshBeacon must run comfortably on
   lower-memory devices, not just on well-equipped ones: the idle target is 128 MB or less.
10. **Maintainable, testable and portable.** A small core that runs with or without Home
   Assistant, tested against real, isolated Reticulum networks.
11. **Honest.** Clear about what works, what does not, what is experimental, and how the project
   is made — including the use of AI assistance.
12. **British English** throughout documentation.

## Who it is for

- Home Assistant users who want resilient alerts and access without relying on cloud services.
- Households in areas with unreliable connectivity, or preparing for outages.
- Existing Reticulum users who already run Home Assistant and want the two to work together.

## Measures of success

- An ordinary Home Assistant user can install MeshBeacon and have a connected, private node in
  **five minutes or less**, without editing a configuration file or opening a terminal, and can
  see it working in MeshBeacon's own interface, measured with real users.
- MeshBeacon never degrades the stability of the Home Assistant instance it runs on.
- Reticulum community members regard MeshBeacon as a good citizen of the network.
