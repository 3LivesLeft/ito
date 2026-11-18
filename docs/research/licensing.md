# Licensing research

Status: **Revised after independent review** · Last updated: 18 November 2026
Decision record: [ADR 0002](../adr/0002-licence.md)

> **This is not legal advice.** It is an engineering-level reading of licence texts. The
> conclusions in §5 (GPL obligations) and §6 (the AI-training condition) in particular would
> benefit from review by someone versed in open-source licensing under English law before the
> first image is published.

Labels follow [feasibility.md](feasibility.md#how-to-read-this-document): **[Verified]**,
**[Assumption]**, **[Recommendation]**, **[Open]**, plus **[Decision]** for maintainer decisions.

## 1. Decision summary

| Topic | Outcome |
|---|---|
| MeshBeacon's original code and documentation | **[Decision]** **Apache-2.0** (maintainer preference following review). `LICENSE` added. |
| Reticulum (RNS) and LXMF | Used as unmodified dependencies under the **Reticulum License** — *not* OSI-approved; see §3. |
| Upstream code in this repository | **None.** No upstream source is copied (§4). |
| Contributor terms | Developer Certificate of Origin (`Signed-off-by`) — no CLA. |
| Publishing container images | **Blocked** until the third-party notices, SBOM and GPL corresponding-source arrangements in §5 are implemented. |

## 2. What MeshBeacon will distribute

There are two very different artefacts, and the licensing position differs between them.

| Artefact | Contents | Licence position |
|---|---|---|
| **Source repository** (GitHub) | MeshBeacon's own code and docs only | Apache-2.0, OSI-approved open source. |
| **Container image** (GHCR, `aarch64` + `amd64`) | MeshBeacon + RNS (+ LXMF later) + Python packages + CPython + Alpine userland + HA base tooling | An **aggregate** of independently licensed components. MeshBeacon's part is Apache-2.0; the image *as a whole* is **not** "Apache-2.0" and must not be described as such. |

**[Recommendation]** Public wording: *"MeshBeacon is open-source software licensed under
Apache-2.0. Its container image also includes third-party components under their own licences —
notably Reticulum and LXMF under the Reticulum License, which is not an OSI-approved open-source
licence. See THIRD_PARTY_NOTICES."*

## 3. Distributed dependencies and compatibility

### 3.1 Python runtime dependencies (v0.1)

**[Verified]** from the installed wheels' `METADATA` (pip 25, CPython 3.13.18, 18 Nov 2026):

| Package | Version | Declared licence | Licence file in wheel? | Compatible with Apache-2.0 MeshBeacon? |
|---|---|---|---|---|
| `rns` | 1.6.0 | Reticulum License | **No** — see note | Yes, as a separate dependency (§3.3) |
| `cryptography` | 50.0.2 | `Apache-2.0 OR BSD-3-Clause` | Yes (`LICENSE`, `LICENSE.APACHE`, `LICENSE.BSD`) + CycloneDX SBOMs | Yes |
| ↳ bundled OpenSSL | 4.0.3 (statically linked; `openssl_version_text()`) | Apache-2.0 **[Assumption]** (OpenSSL ≥ 3 is Apache-2.0) | Via cryptography's SBOM | Yes |
| `cffi` | 2.1.1 | `MIT-0` | Yes | Yes |
| `pycparser` | 3.12 | `BSD-3-Clause` | Yes | Yes |
| `pyserial` | 3.5 | BSD (classifier) | **No** | Yes — but we must supply the notice ourselves |
| `lxmf` (v0.3, not v0.1) | 1.3.0 | Reticulum License | **No** | Yes, as for RNS |

**[Verified] Important:** the `rns` 1.6.0 wheel's `dist-info` contains **no licence file**. Of the
115 `.py` files installed under `RNS/` and `LXMF/`, 78 carry the full Reticulum License text in
their header (including `RNS/__init__.py`), so the notice does travel with the code — but
**MeshBeacon must not rely on pip to satisfy the Reticulum License's notice condition**. Ship the
full licence text explicitly in `THIRD_PARTY_NOTICES` and in the image (§5).

### 3.2 Base image components

**[Verified]** from `home-assistant/docker-base` (`7d9ba08`): the Alpine base image is built from
`alpine:3.24` plus `bash`, `bind-tools`, `ca-certificates`, `curl`, `jq`, `libstdc++`, `tzdata`,
`xz`, a locally built **jemalloc 5.4.0**, **s6-overlay 3.2.3.2**, **bashio 0.19.0** and
**tempio 2026.07.0**; the Python image adds CPython built from signature-verified source.

**[Assumption]** Licences below are from general knowledge and **must be confirmed from the
generated SBOM** (§5) before publication:

| Component | Typical licence | Category |
|---|---|---|
| musl libc | MIT | Permissive |
| BusyBox | GPL-2.0-only | **Copyleft — source obligation** |
| apk-tools | GPL-2.0-only | **Copyleft — source obligation** |
| bash, readline | GPL-3.0-or-later | **Copyleft — source obligation** |
| libstdc++ / libgcc | GPL-3.0 with GCC Runtime Library Exception | Copyleft binary — source obligation for the library itself |
| bind-tools (BIND) | MPL-2.0 | Weak copyleft — source obligation for MPL files |
| curl | curl (MIT-like) | Permissive |
| jq | MIT | Permissive |
| xz / liblzma | 0BSD / public domain | Permissive |
| tzdata | Public domain | — |
| ca-certificates (Mozilla CA data) | MPL-2.0 | Weak copyleft |
| jemalloc | BSD-2-Clause | Permissive |
| s6-overlay, s6, execline, skalibs | ISC | Permissive |
| bashio | MIT | Permissive |
| tempio | Apache-2.0 | Permissive |
| HA base image scripts | Apache-2.0 | Permissive |
| CPython | PSF-2.0 (plus bundled permissive components) | Permissive |

### 3.3 Compatibility conclusion

- **[Verified]** Apache-2.0 contains no "no further restrictions" clause (unlike GPLv3 §7/§10),
  so MeshBeacon's Apache-2.0 code can depend on Reticulum-licensed RNS. The Reticulum License's
  conditions continue to apply **to RNS and LXMF**, and therefore bind anyone who uses, copies or
  redistributes the image's RNS/LXMF components — they do not convert MeshBeacon's own code.
- **[Recommendation]** Because the Reticulum conditions bind users of the image, `DOCS.md` and
  the README must state them in plain language.
- MeshBeacon executes GPL tools in the base image (bash, BusyBox) only as **separate programs**.
  This is "mere aggregation"; it does not make MeshBeacon a derivative of them. It does create
  distribution obligations for those components (§5).
- **[Verified]** Rathole (GPL-3.0), Sideband (CC BY-NC-SA 4.0) and RNode firmware (GPL-3.0) are
  **not** distributed, so impose no obligations. CC BY-NC-SA's non-commercial term is
  incompatible with Apache-2.0 redistribution — another reason never to reuse Sideband code.

## 4. Copying versus depending

Unchanged from Phase 0 and now a hard project rule ([CONTRIBUTING](../../CONTRIBUTING.md)):

- Depend on unmodified upstream packages from PyPI, pinned by version and hash.
- **Copy no upstream source** into this repository, and do not ask AI tools to reproduce,
  translate or paraphrase it.
- Use only RNS's documented interfaces: config format, public API, RPC, CLI utilities.

## 5. Obligations before publishing images

These must all be in place before the first image is pushed to a public registry.

| # | Obligation | Mechanism (recommended) |
|---|---|---|
| O1 | Our Apache-2.0 licence in the image | `/usr/share/doc/meshbeacon/LICENSE` |
| O2 | Reticulum License notice (condition 3) | Full text in `THIRD_PARTY_NOTICES` and `/usr/share/doc/meshbeacon/licenses/rns.txt` (wheel lacks it — §3.1) |
| O3 | Notices for other permissive packages (BSD, MIT, ISC, Apache-2.0, PSF) | Generated `THIRD_PARTY_NOTICES` from the SBOM, including pyserial (no licence file in wheel) |
| O4 | **SBOM** per image digest | Generated in CI (e.g. Syft → SPDX and CycloneDX), attached to the release and as a signed attestation to the image |
| O5 | **Corresponding source for GPL/LGPL/MPL components** (BusyBox, apk-tools, bash, readline, libstdc++, BIND, ca-certificates) | See §5.1 |
| O6 | Licence allow-list in CI | Fail the build if a new component's licence is unknown or not on the allow-list |
| O7 | Reticulum harm and AI conditions communicated to users | Plain-language section in `DOCS.md` |

### 5.1 GPL corresponding source

- **[Verified]** (licence texts) GPL-2.0 §3 requires binary distribution to be accompanied by the
  source, *or* a written offer valid for three years, *or* (§3(c), non-commercial only) passing on
  an offer *you received*. Its final paragraph treats "equivalent access to copy the source code
  from the same place" as sufficient. GPL-3.0 §6(d) allows offering source from a network server
  alongside the object code, provided it remains available as long as the object code is offered.
- **[Assumption]** Relying solely on Alpine's public mirrors is common practice but is **not**
  clearly sufficient for us: we did not receive a written offer (so §3(c) does not apply), and we
  do not control those mirrors' retention.
- **[Recommendation]** For every published image digest, CI produces a **source bundle**: the
  Alpine `aports` build recipes and upstream source tarballs for every GPL/LGPL/MPL package at the
  exact versions in the SBOM, published as a GitHub release asset next to the image and retained
  for at least three years after the last download of that image. The image carries an OCI label
  pointing to it, and `DOCS.md` contains a short written offer as a fallback.
- **[Recommendation]** Keep the GPL footprint small: install no extra GPL packages beyond what
  the HA base image requires.

**[Open] Q-17** — confirm this approach (ideally with an expert) before the first publication.

## 6. The Reticulum License's AI-training condition and AI-assisted development

### 6.1 The text

> "The Software shall not be used, directly or indirectly, in the creation of an artificial
> intelligence, machine learning or language model training dataset, including but not limited
> to any use that contributes to the training or development of such a model or algorithm."

### 6.2 Upstream's own interpretation

**[Verified]** In `AGENTS.md` ("The License In This Context", "Assistance Versus
Machine-Substitution"), the licensor states that the condition "does not forbid the use of
machine-learning technology to *assist* development — no reading of the license could support
that", and that what it forbids is "the *appropriation of the work into the machine itself*". The
same document was itself produced with machine assistance and says so.

### 6.3 Analysis

| Activity | Is it "creation of a training dataset" or a use that "contributes to training or development of a model"? | Assessment |
|---|---|---|
| A developer uses an AI assistant to write, review or explain **MeshBeacon's own** code | No RNS material involved | Outside the condition. |
| An AI assistant reads RNS documentation or public API signatures to integrate with them (inference only) | Use of the Software at inference time; no dataset created; licensor says assistance is permitted | **Permitted**, on the licensor's own reading. |
| An AI assistant reads RNS **source** in a sandbox to verify behaviour (as in Phase 0) | As above, provided the tool provider does **not** retain inputs to train models | **Permitted, conditionally** — depends on the provider's data-use terms (see §6.4). |
| Pasting RNS source into an AI tool whose provider **does** use inputs for model training | The input may become training data: "indirectly … contributes to the training" | **Risk of breaching the condition.** Do not do this. |
| Asking an AI tool to reproduce, translate or port RNS code | Copying/derivation (§4) — and upstream regards machine-generated derivatives as infringing | **Prohibited by project rule.** |
| Publishing MeshBeacon's Apache-2.0 repository, which others might scrape for training | MeshBeacon's own code is not Reticulum-licensed; the repo contains no RNS code | Outside the condition. |
| Publishing an image that contains RNS, which a third party then scrapes for training | Third party's use, not ours; we distribute under the licence's terms | Not a breach by MeshBeacon; the third party would be bound. |
| Building or publishing a corpus of RNS source, docs or chat transcripts containing it | Creation of a potential dataset | **Prohibited by project rule.** |

### 6.4 Rules adopted

**[Recommendation]**, reflected in [CONTRIBUTING](../../CONTRIBUTING.md#ai-assistance) and
[CLAUDE.md](../../CLAUDE.md):

1. AI assistance is permitted for development, review and documentation, and is **disclosed**.
2. AI tools used on this project must operate under terms where **inputs and outputs are not used
   to train models** (for example a commercial/API agreement or a consumer account with training
   opted out). Contributors are responsible for checking their own tool's settings.
3. Prefer giving AI tools RNS's **documentation and public API** rather than its source. Where
   reading source is needed to verify behaviour, do it locally and cite file and revision — never
   reproduce it.
4. Never produce or publish datasets, embeddings or corpora containing RNS or LXMF material.
5. A named human maintainer reviews, understands and answers for every merged change.

**[Decision] Q-15 resolved.** The maintainer has confirmed that AI model training is **disabled**
on both AI accounts used for this project (ChatGPT and Claude). Contributors remain responsible
for their own tools' settings (rule 2).

### 6.5 Copyright in AI-generated material

**[Assumption]** In several jurisdictions purely machine-generated material may not attract
copyright (the US Copyright Office position is cited by upstream; the UK has a specific
computer-generated works provision, CDPA 1988 s.9(3), whose future is under consultation).
Practically: MeshBeacon's Apache-2.0 grant is effective for human-authored and human-edited
material; it is harmless for anything that turns out to be uncopyrightable. This is another reason
for genuine human review and editing of AI drafts.

## 7. Honest disclosure of AI assistance

**[Decision]** Retained from Phase 0: AI assistance is disclosed in the README, CONTRIBUTING and
the Git history (the assistant's commits use its own identity). Attribution is never stripped.

## 8. Name and trademarks

See [naming research](naming.md) and [ADR 0003](../adr/0003-name.md).

## 9. Open licensing questions

| ID | Question |
|---|---|
| Q-15 | **Resolved:** training disabled on the maintainer's ChatGPT and Claude accounts |
| Q-17 | Confirm the GPL corresponding-source approach (§5.1) — **public release gate** (roadmap RG-7) |
| Q-19 | Confirm all base-image component licences from a generated SBOM — **public release gate** (RG-7); SBOM generated in CI from Phase 1 |
| Q-20 | Copyright line: "Copyright 2026 The MeshBeacon contributors" or the maintainer's name? |
