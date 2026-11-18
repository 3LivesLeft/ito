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

- Completely free; no commercialisation, telemetry, analytics or advertising.
- No mandatory third-party cloud services.
- Private and secure by default: no host networking, no public ports, no automatic discovery or
  publication, no unnecessary Home Assistant permissions.
- Uses the unmodified Reticulum reference implementation; implements no protocol or cryptography
  of its own.

## Documentation

| Document | Purpose |
|---|---|
| [Vision](docs/vision.md) | Why MeshBeacon exists and what it is not |
| [Architecture](docs/architecture.md) | Proposed structure and boundaries |
| [Roadmap](docs/roadmap.md) | Provisional versions and v0.1.0 acceptance criteria |
| [Feasibility study](docs/research/feasibility.md) | Phase 0 research with verified facts, assumptions and open questions |
| [Licensing research](docs/research/licensing.md) | Upstream licences and options for MeshBeacon |
| [Threat model](docs/security/threat-model.md) | Assets, threats and controls |
| [Testing strategy](docs/testing/strategy.md) | How we will test against isolated Reticulum networks |
| [ADR 0001](docs/adr/0001-networking-foundation.md) | Build on RNS directly, not on Rathole |

## Credits

MeshBeacon builds on the work of others:

- **Reticulum (RNS)** and **LXMF** by Mark Qvist, licensed under the Reticulum License.
- **Home Assistant**, its Supervisor, base images and builder tooling, by the Open Home Foundation
  and contributors.

MeshBeacon is an independent project and is not affiliated with or endorsed by the Reticulum
project, Home Assistant, the Open Home Foundation or Ratspeak.

## How this project is made

MeshBeacon is directed and maintained by a human maintainer, who is responsible for every change
that is merged. The Phase 0 research and documents were drafted with an AI coding assistant
(Claude, by Anthropic) and committed under its own Git identity so that this is visible in the
history. They are subject to the maintainer's review before they are accepted. See
[CONTRIBUTING.md](CONTRIBUTING.md#ai-assistance).

## Licence

**Not yet chosen.** A licence will be selected after the [licensing research](docs/research/licensing.md)
has been reviewed. Until then, no licence is granted.

## Security

Please see [SECURITY.md](SECURITY.md). Do not report vulnerabilities in public issues.
