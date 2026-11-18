# Vision

> **Stay connected. With or without the internet.**

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
- **Not a cloud service.** Nothing depends on servers run by the MeshBeacon project.
- **Not finished.** MeshBeacon is experimental until v1.0 and should be treated that way.

## Principles

1. **Free for everyone, forever.**
2. **Privacy by default.** Nothing is published, discovered or connected without the user's
   explicit choice.
3. **Security by default.** Least privilege, no privileged containers, no unnecessary Home
   Assistant permissions, no public ports by default.
4. **Reuse upstream.** Build on RNS and LXMF through their public interfaces; never copy or patch
   them.
5. **Native interoperability.** Talk to the wider ecosystem (Sideband, Ratspeak, NomadNet,
   MeshChat) because it is the same protocol — not through bridges or translations.
6. **Good network citizenship.** Be a considerate neighbour on shared networks and shared radio
   spectrum.
7. **Light on resources.** The Home Assistant host comes first.
8. **Maintainable, testable and portable.** A small core that runs with or without Home
   Assistant, tested against real, isolated Reticulum networks.
9. **Honest.** Clear about what works, what does not, what is experimental, and how the project
   is made — including the use of AI assistance.
10. **British English** throughout documentation.

## Who it is for

- Home Assistant users who want resilient alerts and access without relying on cloud services.
- Households in areas with unreliable connectivity, or preparing for outages.
- Existing Reticulum users who already run Home Assistant and want the two to work together.

## Measures of success

- An ordinary Home Assistant user can install MeshBeacon and have a working, private node in
  under ten minutes, without editing a configuration file.
- MeshBeacon never degrades the stability of the Home Assistant instance it runs on.
- Reticulum community members regard MeshBeacon as a good citizen of the network.
