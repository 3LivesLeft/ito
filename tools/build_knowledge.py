"""Generate the immutable dashboard and Nomad bundle from the authored Micron."""

import json
import re
from pathlib import Path


def build(root: Path) -> bytes:
    source = root / "content/knowledge"
    manifest = json.loads((source / "manifest.json").read_text())
    sources = {item["id"]: item for item in json.loads((source / "sources.json").read_text())["sources"]}
    guides = {item["path"].removeprefix("pages/"): item for item in manifest["pages"]}
    files = sorted((source / "pages").rglob("*.mu"))
    names = {
        file.relative_to(source / "pages").as_posix(): "ito-guide--"
        + file.relative_to(source / "pages").as_posix().replace("/", "-")
        for file in files
    }
    if len(set(names.values())) != len(names):
        raise ValueError("Knowledge page filenames collide")
    pages = {}
    for file in files:
        relative = file.relative_to(source / "pages").as_posix()
        name = names[relative]
        if not re.fullmatch(r"[a-z0-9-]{1,40}\.mu", name):
            raise ValueError(f"Invalid Nomad filename: {name}")
        body = re.sub(r":/page/([a-z0-9/-]+\.mu)", lambda match: ":/page/" + names[match[1]], file.read_text())
        guide = guides.get(relative)
        if guide:
            organisations = ", ".join(dict.fromkeys(sources[key]["organisation"] for key in guide["sources"]))
            body += f"\nSources: {organisations}.\n"
            body += "UK-focused emergency reference. Follow emergency services and qualified advice.\n"
            if guide["review_status"] != "reviewed":
                body += "Draft guide. Independent review pending.\n"
        if guide or relative == "index.mu":
            body += "`[About and sources`:/page/ito-guide--about.mu]\n"
        limit = (
            (2048 if relative == "index.mu" else 1024)
            if not guide
            else {"quick": 1024, "standard": 2048, "detailed": 4096}[guide["page_type"]]
        )
        if len(body.encode()) > limit:
            raise ValueError(f"{name} exceeds its {limit}-byte budget")
        pages[name] = {
            "content": body,
            "sources": [
                {field: sources[key][field] for field in ("organisation", "title", "url")} for key in guide["sources"]
            ]
            if guide
            else [],
        }
    pages["ito-guide--about.mu"] = {
        "content": (
            ">About the Ito knowledge library\n"
            "    Ito prepared these summaries using published guidance from the organisations listed on each "
            "guide. The organisations do not endorse this library.\n"
            "\n"
            "    Use the guides as general UK-focused emergency references. Follow instructions from "
            "emergency services and qualified professionals. In immediate danger in the UK, call 999 or 112 "
            "if available. Draft guides are awaiting independent review.\n"
            "\n"
            "    The local Ito dashboard lists the original references. It can display their titles and URLs "
            "offline.\n"
            "    `[Library home`:/page/ito-guide--index.mu]\n"
            "    "
        ),
        "sources": [],
    }
    return (
        json.dumps({"version": manifest["version"], "pages": pages}, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
