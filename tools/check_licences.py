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
    "LGPL-2.0-or-later",
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
    "LicenseRef-Public-Domain",
}
# Packages whose SBOM entry carries no usable SPDX expression, with the licence recorded on review
# (first CI SBOM, 18 November 2026). Entries marked "confirm" are taken from the projects' published
# licences and must be confirmed against the exact upstream versions before public release (RG-7).
REVIEWED = {
    "rns": "LicenseRef-Reticulum",
    "lxmf": "LicenseRef-Reticulum",
    "pyserial": "BSD-3-Clause",  # verified from the 3.5 sdist LICENSE.txt
    "meshbeacon": "Apache-2.0",
    "python": "PSF-2.0",  # CPython built from source by the HA base image
    ".python-rundeps": "NONE-META",  # Alpine virtual package: a dependency list, no content
    "simple launcher": "BSD-3-Clause",  # distlib's Windows launchers vendored inside pip; confirm
    # Go modules compiled into tempio (Apache-2.0, Home Assistant) in the base image; confirm
    "github.com/home-assistant/tempio": "Apache-2.0",
    "dario.cat/mergo": "BSD-3-Clause",
    "github.com/masterminds/goutils": "Apache-2.0",
    "github.com/masterminds/semver/v3": "MIT",
    "github.com/masterminds/sprig/v3": "MIT",
    "github.com/google/uuid": "BSD-3-Clause",
    "github.com/huandu/xstrings": "MIT",
    "github.com/mitchellh/copystructure": "MIT",
    "github.com/mitchellh/reflectwalk": "MIT",
    "github.com/shopspring/decimal": "MIT",
    "github.com/spf13/cast": "MIT",
    "golang.org/x/crypto": "BSD-3-Clause",
}
ALIASES = {
    "Reticulum License": "LicenseRef-Reticulum",
    "LicenseRef-Reticulum-License": "LicenseRef-Reticulum",
    "BSD": "BSD-3-Clause",
    "LicenseRef-BSD": "BSD-3-Clause",  # pyserial: 3-clause text verified
    "PSF": "PSF-2.0",
}
# Syft sometimes turns the operators in an Alpine licence string into LicenseRef tokens.
IGNORED_TOKENS = {"AND", "OR", "WITH", "LicenseRef-AND", "LicenseRef-OR"}
TOKEN = re.compile(r"[A-Za-z0-9.+\-]+(?:-[A-Za-z0-9.+]+)*")


def identifiers(expression: str) -> set[str]:
    expression = ALIASES.get(expression.strip(), expression)
    ids = {t for t in TOKEN.findall(expression) if t not in IGNORED_TOKENS}
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
        if expr == "NONE-META":
            continue
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
