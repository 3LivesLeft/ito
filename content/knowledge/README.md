# Ito knowledge library — work in progress

This first batch is a standalone draft, not a complete or independently safety-reviewed library. Do not publish as emergency guidance until the flagged pages have been independently verified by an appropriate reviewer. See PROGRESS.md for remaining work.

Pages in `pages/` are static Micron using headings and local links only. `manifest.json` describes guide pages; index pages are validated separately. `sources.json` records research sources and limitations. Content is British English; emergency contact numbers currently target the UK. Sources are for maintainers, never loaded by pages.

To add a page, research authoritative current sources, create a short self-contained `.mu`, add it to a category index, and add its metadata and source IDs. Record review status honestly. Byte count is UTF-8 bytes; compute SHA-256 over the exact file. Keep title, path, digest and size in sync. Preserve visible safety warnings. Run `python3 scripts/validate.py --category water` for a focused check and `python3 scripts/validate.py` before delivery. Review changes to existing content and navigation manually. The validator checks the package subset, not semantic correctness or the full Micron grammar. Real client testing and independent safety review remain required.

Each source entry includes the IDs of relevant guide pages. When changing a page's source IDs, update those reverse mappings too. `last_reviewed` records the source-based drafting check; it is not independent professional approval. Update `review_status` only after an appropriate independent reviewer has approved the actual page and record the review externally. Run regression checks with `python3 -m unittest discover -s tests -v` and optionally use `scripts/check_nomad_parser.py` with an installed NomadNet parser. See VALIDATION_REPORT.md for measured file sizes, parser coverage and outstanding safety reviews.

The survival expansion uses original summaries in Ito's Apache-2.0 repository and cites the guidance in `sources.json`. The SurvivalManual-ebook and its underlying field manual informed topic selection. No text, illustrations, or ebook assets from them are bundled. The quick cards use the existing `quick` page type and a 1,024-byte limit after Nomad link rewriting and attribution. Download size and latency depend on the transport and network conditions.

## Practical survival manual

The practical expansion adds 46 full guides, expands 35 existing guides, and adds ten quick cards. Existing paths are retained. Three category indexes use linked section indexes to stay within the 1,024-byte published menu budget. The dashboard reads the same generated bundle as the Nomad page store. Guide titles, descriptions, related guides and source IDs live in the manifest. The dashboard currently navigates by category and links. It has no dedicated search index.

The US Army survival manual informed water procurement, fire, shelter, field navigation, environmental and signalling topics, and priorities under stress. The field hygiene manual informed sanitation layout, containment and personal hygiene. The public JSP 911 author note establishes the British training context. No publicly authorised copy of the JSP 911 procedures was verified for reuse. British practice is sourced separately from Mountain Rescue, the Scouts, Ordnance Survey, forestry and public-health bodies. The e-book and Android adaptations were checked for provenance. The Android repository declares GPL-3.0 and the e-book README distinguishes app, icons and wiki content. No text passages, wording, illustrations, assets or code from either adaptation or the manuals were imported. The new text is original and covered by Ito's Apache-2.0 licence.

The quick cards concentrate on immediate decisions that fit safely on one page. Procedures with important equipment-specific instructions, such as chemical dosing, home canning and fixed wiring, link to the full context or retain their existing source-based guidance. Published sizes below include the rewritten navigation, attribution and review notice.

| New quick card | Bytes |
| --- | ---: |
| Severe bleeding | 772 |
| Heat illness | 719 |
| Distress signalling | 757 |
| Settling raw water | 750 |
| Campfire extinguishing | 756 |
| Tarp shelter | 760 |
| UK grid reference | 737 |
| Emergency toilet | 743 |
| Rescue message | 740 |
| Portable solar input | 771 |

Modern specialist sources take precedence over historical procedures. All new and expanded guides remain marked for independent subject-matter review. Before publication, reviewers should check public health treatment and disposal guidance, clinical guidance for lay responders, local fire and access restrictions, shelter loads and weather, food hygiene, and equipment-specific limits. Loopback transport and page sizes cannot predict radio delivery or airtime.
