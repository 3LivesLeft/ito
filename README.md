# MeshBeacon

**Decentralised connectivity for your home.**

MeshBeacon is a free, open-source, privacy-first, decentralised communications gateway for
[Home Assistant](https://www.home-assistant.io/), powered by the
[Reticulum](https://github.com/markqvist/Reticulum) reference implementation.

> [!WARNING]
> **Experimental — do not depend on this yet.** MeshBeacon is in **Phase 1**: a v0.1.0 local
> prototype that you can build and install as a local Home Assistant app
> ([`meshbeacon/DOCS.md`](meshbeacon/DOCS.md)). No images or releases are published. Physical
> Raspberry Pi validation is still pending ([results so far](docs/testing/phase1-results.md)).

## What it will do

- Run a Reticulum node as a Home Assistant app (formerly "add-on"), on the machine you already
  have — no extra hardware required to start.
- Show node and network health as Home Assistant entities.
- Secure, end-to-end-encrypted messaging with Reticulum messaging apps
  (via [LXMF](https://github.com/markqvist/LXMF)), once its authorisation gates are met.
- Next: v0.3.0 makes it installable from the Home Assistant App store once every release gate
  is met; secure LXMF messaging follows as a later v0.3 milestone, behind security gates.

**Long-term direction (proposed, not committed):** an offline-first community network over
Reticulum, including LoRa — Nomad Network-compatible pages, bulletin boards and offline libraries,
short voice messages and resilient, replicated services. Home Assistant stays a first-class way
to deploy and manage it, but the community services will not depend on it.

See the [vision](docs/vision.md) and the provisional [roadmap](docs/roadmap.md).

## Principles in brief

- Easy to use: connected within five minutes, no configuration files.
- Completely free; no commercialisation, telemetry, analytics or advertising.
- No mandatory third-party cloud services.
- Private and secure by default: no external connections until you choose a peer, no host
  networking, no public ports, no automatic discovery or publication, no unnecessary Home
  Assistant permissions.
- Uses the unmodified Reticulum reference implementation; implements no protocol or cryptography
  of its own.

## Documentation

| Document | Purpose |
|---|---|
| [Vision](docs/vision.md) | Why MeshBeacon exists and what it is not |
| [Architecture](docs/architecture.md) | Proposed structure and boundaries |
| [Roadmap](docs/roadmap.md) | Provisional versions, long-term direction and acceptance criteria |
| [Forward-compatibility review](docs/research/long-term-direction.md) | v0.3 decisions that could constrain the long-term direction |
| [Feasibility study](docs/research/feasibility.md) | Phase 0 research with verified facts, assumptions and open questions |
| [Licensing research](docs/research/licensing.md) | Licence decision, dependency compatibility, AI-training condition, publication obligations |
| [Threat model](docs/security/threat-model.md) | Assets, threats and controls |
| [Testing strategy](docs/testing/strategy.md) | How we will test against isolated Reticulum networks |
| [Phase 1 results](docs/testing/phase1-results.md) | What has been verified so far, and what has not |
| [App documentation](meshbeacon/DOCS.md) | Using the local prototype |
| [Installing the local prototype](docs/install-local-prototype.md) | Step-by-step on Home Assistant OS, without published images |
| [First-run UX](docs/ux/first-run.md) | The five-minute setup path and configuration design |
| [Naming research](docs/research/naming.md) | The existing "MeshBeacon" project and trademark checks |
| [Public peer presets](docs/research/public-peers.md) | Optional public entry points and how they are verified |
| [ADR 0001](docs/adr/0001-networking-foundation.md) | Build on RNS directly, not on Rathole |
| [ADR 0002](docs/adr/0002-licence.md) | Apache-2.0 for MeshBeacon's own work |
| [ADR 0003](docs/adr/0003-name.md) | Keep the name, with disambiguation |
| [ADR 0004](docs/adr/0004-public-peer-presets.md) | Optional verified presets; no default connection |
| [ADR 0005](docs/adr/0005-bounded-recovery.md) | Bounded recovery that cannot loop with the Supervisor watchdog |
| [ADR 0006](docs/adr/0006-local-metrics-api.md) | Read-only local status API, delivered by Supervisor discovery |
| [ADR 0007](docs/adr/0007-separate-identities.md) | Separate identities for transport, messaging and public services |
| [ADR 0008](docs/adr/0008-opt-in-publication.md) | Explicit opt-in for announcements and publication |
| [ADR 0009](docs/adr/0009-public-service-isolation.md) | Public services isolated from Home Assistant and from transport |
| [ADR 0010](docs/adr/0010-v0.3-scope.md) | v0.3.0 is a distribution release; messaging follows behind security gates |

## Credits

MeshBeacon builds on the work of others:

- **Reticulum (RNS)** and **LXMF** by Mark Qvist, licensed under the Reticulum License.
- **Home Assistant**, its Supervisor, base images and builder tooling, by the Open Home Foundation
  and contributors.

MeshBeacon is an independent project and is not affiliated with or endorsed by the Reticulum
project, Home Assistant, the Open Home Foundation or Ratspeak. It is also **not affiliated with the
MeshBeacon disaster-response project** ([meshbeacon.org](https://meshbeacon.org)), which is an
unrelated project with the same name.

## How this project is made

MeshBeacon is directed and maintained by a human maintainer, who is responsible for every change
that is merged. The Phase 0 research and documents were drafted with an AI coding assistant
(Claude, by Anthropic) and committed under its own Git identity so that this is visible in the
history. They are subject to the maintainer's review before they are accepted. See
[CONTRIBUTING.md](CONTRIBUTING.md#ai-assistance).

## Licence

MeshBeacon's own code and documentation are licensed under the
[Apache License, Version 2.0](LICENSE) ([ADR 0002](docs/adr/0002-licence.md)).

Its container images (none published yet) will also contain third-party components under their
own licences. In particular, **Reticulum and LXMF are licensed under the Reticulum License, which
is not an OSI-approved open-source licence**: it forbids use in systems designed to harm people
and use in creating AI training datasets. Those conditions apply to anyone using the image. See
[NOTICE](NOTICE) and the [licensing research](docs/research/licensing.md).

## Security

Please see [SECURITY.md](SECURITY.md). Do not report vulnerabilities in public issues.
