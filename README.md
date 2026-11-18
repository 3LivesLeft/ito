# MeshBeacon

**Stay connected. With or without the internet.**

MeshBeacon is a free, open-source, privacy-first, decentralised communications gateway for
[Home Assistant](https://www.home-assistant.io/), powered by the
[Reticulum](https://github.com/markqvist/Reticulum) reference implementation.

> [!WARNING]
> **Experimental — do not depend on this yet.** MeshBeacon is in **Phase 0 (research and
> design)**. There is no installable software in this repository. The documents here describe
> what we intend to build and why, and are published for review.

## What it will do

- Run a Reticulum node as a Home Assistant app (formerly "add-on"), on the machine you already
  have — no extra hardware required to start.
- Show node and network health as Home Assistant entities.
- Send end-to-end-encrypted notifications from Home Assistant to Reticulum messaging apps
  (via [LXMF](https://github.com/markqvist/LXMF)).
- Later: I2P, LoRa radio via RNode, and carefully authorised off-grid remote automation.

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
| [Roadmap](docs/roadmap.md) | Provisional versions and v0.1.0 acceptance criteria |
| [Feasibility study](docs/research/feasibility.md) | Phase 0 research with verified facts, assumptions and open questions |
| [Licensing research](docs/research/licensing.md) | Licence decision, dependency compatibility, AI-training condition, publication obligations |
| [Threat model](docs/security/threat-model.md) | Assets, threats and controls |
| [Testing strategy](docs/testing/strategy.md) | How we will test against isolated Reticulum networks |
| [First-run UX](docs/ux/first-run.md) | The five-minute setup path and configuration design |
| [Naming research](docs/research/naming.md) | The existing "MeshBeacon" project and trademark checks |
| [Public peer presets](docs/research/public-peers.md) | Optional public entry points and how they are verified |
| [ADR 0001](docs/adr/0001-networking-foundation.md) | Build on RNS directly, not on Rathole |
| [ADR 0002](docs/adr/0002-licence.md) | Apache-2.0 for MeshBeacon's own work |
| [ADR 0003](docs/adr/0003-name.md) | Keep the name, with disambiguation |
| [ADR 0004](docs/adr/0004-public-peer-presets.md) | Optional verified presets; no default connection |

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
