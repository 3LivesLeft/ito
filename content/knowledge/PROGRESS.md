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

## Decisions

Use static Micron with `:/page/...` same-node targets, no external assets; preserve safety content regardless of size. Review status is explicit in the manifest. Page files have non-executable normal file permissions. Metadata stays out of transmitted pages except review date. Main and category indexes are not counted as guide entries. This is a draft, not a complete release.

## Outstanding and next steps

Current batch is complete; next batch is fire, warmth and shelter (10–15 guides including other preparedness topics if needed). Research fire service, NHS and Met Office guidance together. Continue communications, power, food, navigation and self-sufficiency in 10–15 page batches, avoiding duplication, and update this file and commit after each. Target 50–75 guides. Verify rainwater, flooding and every existing warning against direct primary guidance. Expand validator tests for malformed syntax, duplicated IDs, missing category links and malicious paths, and validate real Micron rendering with an actual Nomad parser/client where possible. The present duplicate-page check detects exact content only; it cannot detect paraphrased duplicates. Check source references support each page's actual claims. Generate final size and safety review report. Re-run full validation once when all batches are done. Test LoRa only with actual hardware; otherwise explicitly mark untested. Complete handover, push branch and create draft PR against current develop after completion; do not merge. The current checkpoint is not a complete deliverable.
