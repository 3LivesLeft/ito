# Progress checkpoint — 22 November 2026

Status: INCOMPLETE. Branch `feature/ito-knowledge-library` created from develop commit `3582c86`. Changes confined to content/knowledge. No application or concurrent worktree changed. No PR requested until the complete library is ready.

## Completed batch 1

- Water: 8 guide pages (safe water, sources, boiling, filters, chemical disinfection, storage, rainwater, dehydration).
- Preparedness: 4 guide pages (kit, household plan, power cut, flooding).
- Main index and two category indexes; 12 guides and 15 served files in total.
- Source manifest, initial research and integration notes, restricted-subset validator, hashes and review flags.
- Sources researched: CDC emergency water and storage; Drinking Water Inspectorate boil notices; NHS dehydration; UK Government Be Ready, power cuts and flood protection; London Fire Brigade emergency kit; official Nomad guide and Reticulum manual. See sources.json and TECHNICAL_NOTES.md for links and limitations.
- Validation: `python3 scripts/validate.py --category water` and `python3 scripts/validate.py`: 0 errors, 0 size warnings. No real parser or radio test. This validator checks a deliberately limited subset; it does not verify medical or technical truth.
- ALL 12 pages are safety-critical and require independent subject-matter review before release. Source-backed drafting is not independent review. Rainwater non-potable collection and flood instructions need additional targeted authoritative source verification.

## Completed batch 2 — first aid and health

- 12 guides: emergency assessment, adult CPR/AED, child and baby CPR, severe bleeding, burns, choking for adults and children, choking for babies, hypothermia, heat illness, fractures, wounds and supplies. First-aid index and direct emergency cross-links added.
- Sources added: Resuscitation Council UK adult and paediatric 2025 guidance and FAQ; NHS burns, hypothermia, heat illness and cuts; NHS 111 Wales first aid; St John Ambulance bleeding, fractures and first-aid supplies. See sources.json. Source-based drafting is not independent review: all 12 new guides require clinical review before publication, with special attention to paediatric CPR and choking, burns and tourniquets.
- Focused validation: `python3 scripts/validate.py --category first-aid`; 0 errors, 0 size warnings. No Nomad parser, connectivity or radio test.
- Total so far: 24 guides, 28 served files; all 24 guides flagged for independent safety review.

## Completed batch 3 — fire, warmth and shelter

- 11 guides: staying warm without heating, preventing hypothermia, outdoor shelter, outdoor fires, house fire escape, carbon monoxide, insulation, extreme heat, alarms, camping fire safety and wildfire response. Added category index and direct related-page links, including links to the existing first-aid pages.
- Researched the NHS, Met Office, London Fire Brigade, UK Government Fire Kills/Be Ready guidance, Mid and West Wales Fire and Rescue Service, Mountain Rescue England and Wales and AdventureSmartUK. References and source limitations are in sources.json. Mountain Rescue shelter guidance includes a disclosed commercial partnership; only its general safety advice was used.
- All 11 new pages require independent safety review, especially emergency fire escape, outdoor fire and carbon monoxide instructions. Local building evacuation plans and radio/contact availability vary.
- Focused validation: `python3 scripts/validate.py --category shelter`: 0 errors and 0 size warnings. No real Nomad rendering or radio test.
- Total: 35 guides and 40 served files; all 35 guide entries remain flagged for independent safety review.

## Completed batch 4 — emergency communications

- 12 guides: emergency help, Reticulum, Nomad Network, LoRa, network relays, offline communications, radio help, signal, antennas, radio power, household communications plans and UK radio rules. Added category index and direct related links.
- Researched official Reticulum and Nomad documentation, Ofcom IR 2030 and amateur/PMR446 guidance, Ofcom outage guidance, Semtech's LoRa FAQ, UK emergency planning guidance, and antenna safety guidance. See sources.json for specific URLs and limitations.
- All 12 communications pages require independent safety/technical and relevant legal review before publication. UK radio conditions and emergency services capabilities can change. Emergency SMS requires prior registration and a mobile network; no unverified claim that a mesh contacts 999 directly.
- Corrected the existing first-aid assessment page to call 999 immediately for an unresponsive person before checking breathing, as specified by RCUK's 2025 adult basic life support guidance. Page version bumped; remains subject to independent clinical review. Focused validation for communications and first aid: 0 errors, 0 size warnings. Actual Nomad and LoRa tests still outstanding.
- Total: 47 guides, 53 served files; all 47 guide entries currently require independent review.

## Completed batch 5 — electricity and emergency power

- 11 guides: preparing for a power cut, battery capacity, runtime, power stations, portable solar, household solar, essential loads, battery safety, fuel generators, electrical hazards and medical equipment. Added a category index and related-page links.
- Researched Ofgem, UK Government and NHS, London and Buckinghamshire fire services, HSE Northern Ireland, National Grid Electricity Distribution, Electrical Safety First, the Food Standards Agency, US Department of Energy and a power station manufacturer. Source limitations are recorded in sources.json; manufacturer-specific solar input figures are not generalised.
- All 11 pages need independent electrical, fire-safety and where appropriate clinical review before publication. Special review: generator isolation and site-specific exhaust safety, standby-system earthing and protective devices, lithium batteries, and medical-device compatibility. Backup power must be designed for the installation and equipment; no home wiring instructions are included.
- Focused validation: `python3 scripts/validate.py --category power`: 0 errors, 0 size warnings. No physical equipment, Nomad renderer or LoRa tests conducted.
- Total: 58 guides, 65 served files; all 58 guide entries currently require independent review.

## Decisions

Use static Micron with `:/page/...` same-node targets, no external assets; preserve safety content regardless of size. Review status is explicit in the manifest. Page files have non-executable normal file permissions. Metadata stays out of transmitted pages except review date. Main and category indexes are not counted as guide entries. This is a draft, not a complete release.

## Outstanding and next steps

Current batch is complete; next batch is food and cooking (10–15 guides, including remaining priority preparedness or self-sufficiency material as appropriate). Research food storage, power-cut food safety and outdoor cooking together using FSA and fire service guidance. Then cover navigation and remaining self-sufficiency priorities in a final batch. Avoid duplication, target roughly 50–75 guides but prioritise completeness and safety, and update this file and commit after each. Target 50–75 guides. Verify rainwater, flooding and every existing warning against direct primary guidance. Expand validator tests for malformed syntax, duplicated IDs, missing category links and malicious paths, and validate real Micron rendering with an actual Nomad parser/client where possible. The present duplicate-page check detects exact content only; it cannot detect paraphrased duplicates. Check source references support each page's actual claims. Generate final size and safety review report. Re-run full validation once when all batches are done. Test LoRa only with actual hardware; otherwise explicitly mark untested. Complete handover, push branch and create draft PR against current develop after completion; do not merge. The current checkpoint is not a complete deliverable.
