# Validation report — draft, 22 November 2026

## Inventory

78 guides across nine categories: water 8; preparedness 7; first aid 12; shelter 11; communications 12; power 11; food 7; navigation 6; self-sufficiency 4. Including the main index and nine category indexes, 88 Micron files total 76,205 UTF-8 bytes, averaging 866 bytes. Largest: `pages/communications/licensing.mu`, 1,098 bytes. No files exceed their declared targets. Targets are design goals, not protocol limits.

## Checks

- Full static validation: 0 errors and 0 size warnings. The validator checks the supported subset of markup, sources, metadata, hashes, navigation and link targets. It detects exact duplicate content, not paraphrases, and is not a safety or legal assessment.
- Seven validator regression tests pass: missing sources, duplicate IDs, malformed markup, broken links, path traversal, external URLs and altered content.
- The actual NomadNet Micron parser at commit `c9dbc11d9d7cd314a2ab3207ddf9a1d0d4becf8b`, with a mock text UI and urwid, parsed and rendered all 88 files at 40 columns and returned all 365 expected link targets. This is a parser/widget check, not a running node, browser click-through, remote retrieval or radio test. `scripts/check_nomad_parser.py` can repeat it if NomadNet and its dependencies are installed.
- All 78 guides are conservatively classified safety-critical and flagged `requires_independent_review`. Research and automated checks do not replace review by qualified first-aid, public-health, food, fire, electrical, outdoor and radio specialists. Do not treat this draft as publication-ready until review is complete. `last_reviewed` records the source-based drafting check, not independent sign-off.
- No actual LoRa hardware, signal-strength measurements, throughput, multi-hop, live hosting, interrupted transfer, caching or internet-disconnected integration has been tested. These remain integration acceptance tests.

## Illustrative transfer times

Payload-only seconds = UTF-8 bytes × 8 ÷ assumed effective application throughput. For the 1,098-byte largest page, the estimates at 100, 500, 1,000 and 2,000 bits/s are 87.84, 17.57, 8.78 and 4.39 seconds respectively. At the same rates the 76,205-byte complete page tree would take 6,096.4, 1,219.28, 609.64 and 304.82 seconds of ideal payload transfer. These are not measurements or forecasts; they exclude session setup, pauses, discovery and other delays. Effective rates already incorporate whatever protocol overhead is assumed in the rate: do not deduct it twice. Shared airtime, retransmissions, duty-cycle waits and multiple hops can increase actual elapsed time and network occupancy significantly. Retrieving only the required page is preferable to a full transfer.
