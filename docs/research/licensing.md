# Licensing research

Status: **Draft for review** · Research date: 18 November 2026

> **This is not legal advice.** It is an engineering-level reading of licence texts, written to
> inform a decision by the maintainer. Where the conclusion matters (in particular §4 and §6),
> independent review is recommended — ideally by someone familiar with open-source licensing
> under English law.

Labels follow [feasibility.md](feasibility.md#how-to-read-this-document): **[Verified]**,
**[Assumption]**, **[Recommendation]**, **[Open]**.

**No licence has been selected or added to this repository.** Per the Phase 0 brief, that decision
waits until this document has been reviewed. Until a licence is added, the repository is "all
rights reserved" by default, which prevents others from legally reusing it — so this should not
remain unresolved for long.

## 1. Upstream licences (verified)

| Component | How MeshBeacon would use it | Licence (verified from `LICENSE` at the revisions in feasibility §1) |
|---|---|---|
| RNS (`rns` on PyPI) | Runtime dependency, unmodified | **Reticulum License** (PyPI metadata: "Reticulum License") |
| LXMF (`lxmf` on PyPI) | Runtime dependency (v0.3), unmodified | **Reticulum License** |
| `cryptography` | Transitive runtime dependency | Apache-2.0 OR BSD-3-Clause **[Assumption]** — from general knowledge; confirm from the wheel metadata in Phase 1 SBOM |
| `pyserial` | Transitive runtime dependency | BSD-3-Clause **[Assumption]** — confirm in SBOM |
| HA base images (`docker-base`) | Container base image | Apache-2.0 (plus Alpine package licences) |
| HA builder actions | CI only | Apache-2.0 |
| HA Supervisor | Not distributed by us | Apache-2.0 |
| Rathole | **Not used** (see ADR 0001) | GPL-3.0-or-later |
| Sideband | **Not used**; interoperability target only | CC BY-NC-SA 4.0 |
| RNode firmware | **Not distributed**; users flash their own devices (v0.5) | GPL-3.0 |
| rsReticulum / Ratspeak | Interoperability target only | Reticulum License (derivative; "Additions and modifications Copyright (c) 2026 Ratspeak LLC") |

## 2. The Reticulum License

**[Verified]** Full text in `LICENSE` of the Reticulum and LXMF repositories. It is the MIT licence
grant ("use, copy, modify, merge, publish, distribute, sublicense, and/or sell") subject to three
conditions:

1. "The Software shall not be used in any kind of system which includes amongst its functions the
   ability to purposefully do harm to human beings."
2. "The Software shall not be used, directly or indirectly, in the creation of an artificial
   intelligence, machine learning or language model training dataset, including but not limited
   to any use that contributes to the training or development of such a model or algorithm."
3. The copyright notice and permission notice "shall be included in all copies or substantial
   portions of the Software."

**[Verified]** Upstream's own commentary (`AGENTS.md` / `docs/source/brandolinis.rst`, "What The
Reticulum License Is") states that the licence applies from RNS 0.9.4 (15 April 2025) onwards, that
**the protocol itself is dedicated to the public domain**, and that the licence covers the
reference *implementation*.

### 2.1 Consequences for MeshBeacon

- **Not OSI-approved.** Conditions 1 and 2 are field-of-use restrictions, which the Open Source
  Definition (criterion 6) does not allow. Upstream disputes that this makes RNS "not open source";
  MeshBeacon need not take a side, but should describe RNS accurately — e.g. "source-available
  under the Reticulum License" or simply "licensed under the Reticulum License" — and avoid
  claiming the *whole distributed image* is OSI open source.
- **Condition 1 (harm).** MeshBeacon's purpose (resilient communications, smart-home monitoring)
  does not include purposefully harming humans. **[Recommendation]** v0.6 remote automation must be
  designed so that MeshBeacon is not marketed or documented for uses that could fall within it (for
  example control of security or weapons systems). Document the condition for users, because it
  binds *them* too.
- **Condition 2 (AI training).** MeshBeacon does not create training datasets. **[Open] Q-15**:
  this Phase 0 research was performed by an AI assistant reading RNS source for analysis
  (inference, not training). Our reading is that this is not "creation of a … training dataset",
  but the maintainer should form their own view. **[Recommendation]** Do not publish bulk copies
  or derived corpora of RNS source in this repository.
- **Condition 3 (notice).** The published container image will contain RNS and LXMF.
  **[Recommendation]** Include their `LICENSE` files in the image (pip does this inside the
  installed `*.dist-info`, **[Assumption]** — verify in Phase 1) *and* in a top-level
  `THIRD_PARTY_NOTICES` file in the image and repository.

## 3. Copying versus depending

**[Verified]** Upstream distinguishes sharply between *depending on / speaking the protocol*
(welcome) and *deriving from the implementation* (subject to the licence, and — upstream argues —
plain copyright infringement if machine-generated without attribution).

**[Recommendation]** MeshBeacon policy:

- Depend on unmodified upstream packages from PyPI, pinned by version and hash.
- **Copy no upstream source** (RNS, LXMF, Rathole, Sideband, NomadNet, RNode firmware) into this
  repository — not even "small" snippets — and do not ask AI tools to reproduce or translate it.
- Use only RNS's documented public API, configuration format and command-line utilities.
- If a fix in RNS is ever needed, carry it as a clearly separated patch with attribution, under
  the Reticulum License — and prefer not to.

## 4. Compatibility analysis for MeshBeacon's own licence

MeshBeacon's Python code will `import RNS` and run in the same process (or a managed child process
running RNS). Whether importing a Python module creates a "combined work" is debated; the FSF's
position is that it generally does. We assume the conservative view.

| Candidate licence for MeshBeacon | Compatible with depending on Reticulum-licensed RNS? | Notes |
|---|---|---|
| **MIT** | **Yes.** Permissive; RNS's extra conditions continue to apply to RNS itself. | Simplest; matches the ecosystem's MIT heritage; no patent grant. |
| **Apache-2.0** | **Yes**, same reasoning. | Explicit patent grant and patent-retaliation clause; NOTICE mechanism; used by HA. |
| **BSD-2/3-Clause** | Yes. | Similar to MIT. |
| **Reticulum License** (adopt it for MeshBeacon) | Yes, by definition. | Aligns with ecosystem values; not OSI-approved; would bind MeshBeacon users to the harm/AI conditions for MeshBeacon's code too. |
| **GPL-3.0 / AGPL-3.0** | **Problematic.** GPLv3 §7 and §10 forbid imposing "further restrictions"; RNS's field-of-use conditions are restrictions that cannot be removed. Distributing a GPL-3.0 MeshBeacon combined with RNS would leave recipients unable to receive the combined work under GPL terms alone. | **Not recommended.** Note: Rathole (GPL-3.0 importing RNS) appears to have exactly this tension — another reason not to depend on it. |
| **MPL-2.0** | Probably yes (file-level copyleft). | Adds complexity with little benefit here. |
| CC licences | Not suitable for software. | Sideband's CC BY-NC-SA 4.0 "non-commercial" term is also incompatible with MIT/Apache distribution. |

**[Recommendation]** Choose between **MIT** and **Apache-2.0** for MeshBeacon's code, with
documentation under **CC BY 4.0** or the same licence as the code. Apache-2.0 is marginally
preferred for its explicit patent grant and alignment with Home Assistant's own licensing;
MIT is preferred if the maintainer values maximum simplicity and closeness to the Reticulum
licence family. Adopting the Reticulum License is a legitimate values-based choice but would make
MeshBeacon itself non-OSI and may deter some contributors and distributors.

**[Open] Q-1** — maintainer decision.

## 5. Distribution restrictions and obligations

| Channel | Obligation |
|---|---|
| GitHub repository (source) | Our licence file; `THIRD_PARTY_NOTICES` listing dependencies and their licences. |
| Container image (GHCR, per-arch + multi-arch manifest) | Includes RNS/LXMF (Reticulum License notice required), Python, Alpine packages (various, including GPL-licensed BusyBox and musl under MIT) — **[Assumption]**: the HA base image already carries the Alpine packages' licence files; confirm. Provide an SBOM (SPDX or CycloneDX) per image. |
| Source offer for GPL components in the base image | BusyBox is GPL-2.0. Distributing the binary image arguably triggers a source-availability obligation for it. **[Assumption]** Pointing to Alpine's and HA's public sources is the common practice; confirm acceptability. **[Open] Q-17.** |
| Future RNode firmware handling (v0.5) | Do **not** bundle firmware binaries; rely on the user's own `rnodeconf` workflow. If ever bundled: GPL-3.0 source obligations apply. |

**[Recommendation]** Generate an SBOM in CI for every image and fail the build on new
dependencies with unknown or incompatible licences (licence allow-list).

## 6. Name and trademark considerations

- **[Verified]** "MeshBeacon" is used by an existing GitHub organisation in the mesh/emergency
  communications space (see [feasibility §4.2](feasibility.md#42-naming-conflicts)).
- **[Assumption]** No registered trademark search has been performed. **[Open] Q-3.**
- "Reticulum", "Home Assistant", "Sideband" and "Ratspeak" are names of other projects.
  **[Recommendation]** Use them only descriptively ("for Home Assistant", "powered by Reticulum"),
  never in a way that implies endorsement, and avoid their logos. Home Assistant publishes brand
  guidelines; check them before designing an icon **[Open] Q-18**.

## 7. Contributor terms

**[Recommendation]** Use a **Developer Certificate of Origin** (`Signed-off-by:`) rather than a
CLA, consistent with "completely free, no commercialisation". Contributors must confirm they
have not copied incompatible code, and must disclose substantive AI assistance (see
[CONTRIBUTING.md](../../CONTRIBUTING.md)).

## 8. Summary of open licensing questions

| ID | Question |
|---|---|
| Q-1 | MeshBeacon licence: MIT, Apache-2.0, or Reticulum License? |
| Q-3 | Name/trademark conflict with "MeshBeacon" organisation |
| Q-15 | Maintainer's view on AI-assisted development and the Reticulum License's AI condition |
| Q-17 | Source-offer approach for GPL components in the base image |
| Q-18 | Home Assistant brand guideline constraints for icon/logo |
