# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_licences", Path(__file__).parents[2] / "tools" / "check_licences.py"
)
cl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cl)


def sbom(*pkgs):
    return {"packages": [{"SPDXID": f"SPDXRef-{i}", **p} for i, p in enumerate(pkgs)]}


def test_allowed_and_reviewed():
    assert (
        cl.check(
            sbom(
                {"name": "musl", "licenseDeclared": "MIT"},
                {"name": "busybox", "licenseDeclared": "GPL-2.0-only"},
                {"name": "cryptography", "licenseDeclared": "Apache-2.0 OR BSD-3-Clause"},
                {"name": "rns", "licenseDeclared": "NOASSERTION"},
                {"name": "libstdc++", "licenseDeclared": "GPL-3.0-or-later WITH GCC-exception-3.1"},
            )
        )
        == []
    )


def test_unknown_and_disallowed_fail():
    problems = cl.check(
        sbom(
            {"name": "mystery", "licenseDeclared": "NOASSERTION"},
            {"name": "agpl-thing", "licenseDeclared": "AGPL-3.0-only"},
            {"name": "nc-thing", "licenseDeclared": "CC-BY-NC-SA-4.0"},
        )
    )
    assert len(problems) == 3


def test_first_ci_sbom_findings_resolved_by_review():
    """Entries seen in the first CI SBOM of the HA base image (18 November 2026)."""
    assert (
        cl.check(
            sbom(
                {"name": ".python-rundeps", "licenseDeclared": "NOASSERTION"},
                {"name": "Simple Launcher", "licenseDeclared": "NOASSERTION"},
                {"name": "github.com/Masterminds/semver/v3", "licenseDeclared": "NOASSERTION"},
                {"name": "keyutils-libs", "licenseDeclared": "LGPL-2.0-or-later"},
                {"name": "pyserial", "licenseDeclared": "LicenseRef-BSD"},
                {"name": "python", "licenseDeclared": "NOASSERTION"},
                {"name": "rns", "licenseDeclared": "LicenseRef-Reticulum-License"},
                {"name": "tzdata", "licenseDeclared": "LicenseRef-Public-Domain"},
                {"name": "xz", "licenseDeclared": "0BSD AND LicenseRef-AND LicenseRef-Public-Domain"},
            )
        )
        == []
    )


def test_new_unreviewed_go_module_still_fails():
    assert cl.check(sbom({"name": "github.com/example/unknown", "licenseDeclared": "NOASSERTION"}))


def test_new_strong_copyleft_or_nc_still_fails():
    assert cl.check(sbom({"name": "x", "licenseDeclared": "AGPL-3.0-only"}))
    assert cl.check(sbom({"name": "y", "licenseDeclared": "LicenseRef-Unknown-Thing"}))
