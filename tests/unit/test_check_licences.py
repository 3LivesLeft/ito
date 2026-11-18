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
