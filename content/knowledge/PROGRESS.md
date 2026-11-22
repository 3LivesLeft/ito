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

## Decisions

Use static Micron with `:/page/...` same-node targets, no external assets; preserve safety content regardless of size. Review status is explicit in the manifest. Page files have non-executable normal file permissions. Metadata stays out of transmitted pages except review date. Main and category indexes are not counted as guide entries. This is a draft, not a complete release.

## Outstanding and next steps

Current batch is complete; next batch is first aid and health (10–12 guides). Research NHS, Resuscitation Council UK, British Red Cross and St John Ambulance as a group, including adult/child differences; independently review each safety-critical instruction. Continue shelter, communications, power, food, navigation and self-sufficiency in 10–15 page batches, avoiding duplication, and update this file and commit after each. Target 50–75 guides. Verify rainwater, flooding and every existing warning against direct primary guidance. Expand validator tests for malformed syntax, duplicated IDs, missing category links and malicious paths, and validate real Micron rendering with an actual Nomad parser/client where possible. The present duplicate-page check detects exact content only; it cannot detect paraphrased duplicates. Check source references support each page's actual claims. Generate final size and safety review report. Re-run full validation once when all batches are done. Test LoRa only with actual hardware; otherwise explicitly mark untested. Complete handover, push branch and create draft PR against current develop after completion; do not merge. The current checkpoint is not a complete deliverable.
