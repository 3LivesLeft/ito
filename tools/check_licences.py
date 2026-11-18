#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Licence compliance check over an SPDX JSON SBOM (licensing research §5, O6).

Every package must have a licence expression whose identifiers are all on the allow-list, or be
named in the reviewed exceptions below. Unknown or disallowed licences fail the check, so a new
dependency cannot slip into the image unreviewed.

Usage: check_licences.py sbom.spdx.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ALLOWED = {
    # Permissive
    "Apache-2.0",
    "MIT",
    "MIT-0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "0BSD",
    "Zlib",
    "PSF-2.0",
    "Python-2.0",
    "curl",
    "X11",
    "Unicode-DFS-2016",
    "Unicode-3.0",
    "BSD-3-Clause-Clear",
    "OpenSSL",
    "SSLeay-standalone",
    "CC0-1.0",
    "Unlicense",
    "Public-Domain",
    "blessing",
    "bzip2-1.0.6",
    # Weak copyleft (separate components; source obligations handled by the source bundle, RG-7)
    "MPL-2.0",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0-or-later",
    # Copyleft programs in the base image, used only as separate programs (mere aggregation);
    # corresponding source is published with each image (licensing §5.1, release gate RG-7)
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "GCC-exception-3.1",
    # Reviewed non-OSI licence (ADR 0002): Reticulum and LXMF
    "LicenseRef-Reticulum",
}
# Names of packages whose metadata does not carry an SPDX expression, with their reviewed licence.
REVIEWED = {
    "rns": "LicenseRef-Reticulum",
    "lxmf": "LicenseRef-Reticulum",
    "pyserial": "BSD-3-Clause",
    "meshbeacon": "Apache-2.0",
}
ALIASES = {"Reticulum License": "LicenseRef-Reticulum", "BSD": "BSD-3-Clause", "PSF": "PSF-2.0"}
TOKEN = re.compile(r"[A-Za-z0-9.+\-]+(?:-[A-Za-z0-9.+]+)*")


def identifiers(expression: str) -> set[str]:
    expression = ALIASES.get(expression.strip(), expression)
    ids = {t for t in TOKEN.findall(expression) if t not in {"AND", "OR", "WITH"}}
    return {ALIASES.get(i, i) for i in ids}


def package_licence(pkg: dict) -> str:
    for key in ("licenseConcluded", "licenseDeclared"):
        value = pkg.get(key)
        if value and value not in ("NOASSERTION", "NONE"):
            return str(value)
    return REVIEWED.get(str(pkg.get("name", "")).lower(), "")


def check(sbom: dict) -> list[str]:
    problems = []
    for pkg in sbom.get("packages", []):
        name = pkg.get("name", "?")
        if pkg.get("SPDXID") == "SPDXRef-DOCUMENT" or name in ("", "/"):
            continue
        expr = package_licence(pkg)
        if not expr:
            problems.append(f"{name} {pkg.get('versionInfo', '')}: no licence information")
            continue
        bad = identifiers(expr) - ALLOWED
        if bad:
            problems.append(f"{name} {pkg.get('versionInfo', '')}: not on the allow-list: {', '.join(sorted(bad))}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    sbom = json.loads(Path(argv[1]).read_text())
    problems = check(sbom)
    total = len([p for p in sbom.get("packages", []) if p.get("SPDXID") != "SPDXRef-DOCUMENT"])
    if problems:
        print(f"Licence check FAILED for {len(problems)} of {total} packages:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"Licence check passed for {total} packages.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
