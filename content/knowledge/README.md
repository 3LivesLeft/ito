# Ito knowledge library — work in progress

This first batch is a standalone draft, not a complete or independently safety-reviewed library. Do not publish as emergency guidance until the flagged pages have been independently verified by an appropriate reviewer. See PROGRESS.md for remaining work.

Pages in `pages/` are static Micron using headings and local links only. `manifest.json` describes guide pages; index pages are validated separately. `sources.json` records research sources and limitations. Content is British English; emergency contact numbers currently target the UK. Sources are for maintainers, never loaded by pages.

To add a page, research authoritative current sources, create a short self-contained `.mu`, add it to a category index, and add its metadata and source IDs. Record review status honestly. Byte count is UTF-8 bytes; compute SHA-256 over the exact file. Keep title, path, digest and size in sync. Preserve visible safety warnings. Run `python3 scripts/validate.py --category water` for a focused check and `python3 scripts/validate.py` before delivery. Review changes to existing content and navigation manually. The validator checks the package subset, not semantic correctness or the full Micron grammar. Real client testing and independent safety review remain required.
