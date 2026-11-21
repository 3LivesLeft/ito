# SPDX-License-Identifier: Apache-2.0
"""Publishing guards for every workflow (decision D3; M1.2 review L-5 and M-2).

Nothing may publish before M2's approval. The primary control is structural: every workflow has
exactly ``permissions: contents: read`` and no job widens it, so the workflow token cannot write
packages, releases or tags, and no workflow uses secrets, environments, reusable workflows or
local actions (whose steps this test could not see). On top of that, steps are checked for every
publishing route the maintainers know of; the list is defence in depth, not the control.

``publishing_problems`` is also exercised on synthetic workflows, so the guard itself is tested.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
# The ONLY workflow files that may ever publish (M2, after the maintainer's approval). Empty until
# then. Every workflow not named here must stay exactly read-only; one named here may give write
# permissions only to jobs that pass promotion_problems (protected environment, no build, the
# verified archive checked against digests.json).
PUBLISHING_WORKFLOWS: frozenset[str] = frozenset()

# Commands that publish, push, sign or release.
PUBLISH_COMMANDS = re.compile(
    r"docker\s+(?:image\s+)?push|docker\s+manifest\s+push|docker\s+login|--push\b|push\s*[:=]\s*true"
    r"|type\s*=\s*registry|imagetools\s+create|skopeo\s+(?:copy|sync)|crane\s+(?:push|copy|cp|append|mutate)"
    r"|oras\s+(?:push|attach|copy|cp)|regctl\s+(?:image\s+(?:copy|import|mod)|artifact\s+put|manifest\s+put)"
    r"|cosign\s+(?:sign|attest|attach|upload|copy)|notation\s+sign|\bgh\s+release\b|\bgh\s+api\b"
    r"|upload-release-asset|uploads\.github\.com|api\.github\.com|git\s+push|git\s+tag"
    r"|twine\s+upload|npm\s+publish",
    re.IGNORECASE,
)
# Actions that publish or sign, matched in `uses:`.
PUBLISH_ACTIONS = re.compile(
    r"login-action|build-push-action|cosign|sigstore|attest-build-provenance|release|upload-release"
    r"|push-to|ghcr|publish|deploy|pages",
    re.IGNORECASE,
)
# Triggers that could run with more rights or on publication events.
FORBIDDEN_TRIGGERS = {"release", "pull_request_target", "workflow_run", "registry_package", "workflow_call"}


def _triggers(workflow: dict[str, Any]) -> set[str]:
    on = workflow.get("on", workflow.get(True))  # YAML 1.1 reads a bare `on` as True
    if isinstance(on, str):
        return {on}
    return set(on or [])


def publishing_problems(workflow: dict[str, Any]) -> list[str]:
    """Why ``workflow`` could publish, sign or escalate; empty if it cannot."""
    problems: list[str] = []
    if workflow.get("permissions") != {"contents": "read"}:
        problems.append("top-level permissions must be exactly contents: read")
    problems += [f"trigger {t}" for t in sorted(_triggers(workflow) & FORBIDDEN_TRIGGERS)]
    text = yaml.safe_dump(workflow)
    if "secrets." in text or "secrets:" in text:
        problems.append("uses secrets")
    for name, job in (workflow.get("jobs") or {}).items():
        if "permissions" in job:
            problems.append(f"{name}: jobs must not set permissions")
        if "environment" in job:
            problems.append(f"{name}: deployment environment")
        if "uses" in job:
            problems.append(f"{name}: reusable workflow (its steps are not checked here)")
        for step in job.get("steps", []):
            uses, run, with_ = str(step.get("uses", "")), str(step.get("run", "")), step.get("with") or {}
            if uses.startswith("./") or uses.startswith("docker://"):
                problems.append(f"{name}: local or container action {uses} (not checked here)")
            if uses and PUBLISH_ACTIONS.search(uses.split("@", 1)[0]):
                problems.append(f"{name}: publishing action {uses}")
            if PUBLISH_COMMANDS.search(run) or PUBLISH_COMMANDS.search(yaml.safe_dump(with_)):
                problems.append(f"{name}: publishing command in {step.get('name') or uses or run[:40]!r}")
            if with_.get("push") in (True, "true") or with_.get("outputs"):
                problems.append(f"{name}: push or outputs in {uses}")
    return problems


def promotion_problems(workflow: dict[str, Any]) -> list[str]:
    """M-2: a job that can publish (M2) must promote the verified archive, never build one.

    Applies to any job that will hold ``packages: write``; none exists before M2, so today this is
    exercised on synthetic workflows only. It stays in force when publishing is written.
    """
    problems = []
    for name, job in (workflow.get("jobs") or {}).items():
        permissions = {**(workflow.get("permissions") or {}), **(job.get("permissions") or {})}
        if permissions.get("packages") != "write":
            continue
        runs = "\n".join(str(step.get("run", "")) for step in job.get("steps", []))
        uses = " ".join(str(step.get("uses", "")) for step in job.get("steps", []))
        if re.search(r"docker\s+(?:buildx\s+)?build|buildah\s+bud|kaniko", runs) or "build-push-action" in uses:
            problems.append(f"{name}: builds an image in the publishing job (promote the verified archive)")
        if "verify_image.py" not in runs or "--expect-digests" not in runs:
            problems.append(f"{name}: does not check the published image against digests.json")
        if "environment" not in job:
            problems.append(f"{name}: not behind the protected release environment")
    return problems


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_can_publish_sign_or_escalate(path):
    """Every non-publishing workflow keeps exactly read-only permissions (M1.2 re-review)."""
    workflow = yaml.safe_load(path.read_text())
    assert path.name not in PUBLISHING_WORKFLOWS  # none is exempt before M2
    assert publishing_problems(workflow) == [], path
    assert promotion_problems(workflow) == [], path


def test_publishing_is_not_yet_approved():
    """M2 needs the maintainer's approval. Adding a file here is that change, and it is reviewed."""
    assert frozenset() == PUBLISHING_WORKFLOWS
    assert all((ROOT / ".github" / "workflows" / name).exists() for name in PUBLISHING_WORKFLOWS)


def _wf(steps: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"on": {"push": {}}, "permissions": {"contents": "read"}, "jobs": {"j": {"steps": steps, **extra}}}


@pytest.mark.parametrize(
    "workflow",
    [
        _wf([{"run": "docker buildx build --output type=registry,name=ghcr.io/x/y ."}]),
        _wf([{"run": "docker buildx build --output type=image,name=ghcr.io/x/y,push=true ."}]),
        _wf([{"run": "skopeo copy --all oci-archive:c.tar docker://ghcr.io/x/y:1"}]),
        _wf([{"run": "crane push c.tar ghcr.io/x/y:1"}]),
        _wf([{"run": "oras push ghcr.io/x/y:1 c.tar"}]),
        _wf([{"run": "regctl image import ghcr.io/x/y:1 c.tar"}]),
        _wf([{"run": "docker buildx imagetools create -t ghcr.io/x/y:1 ghcr.io/x/y@sha256:0"}]),
        _wf([{"run": "cosign sign --yes ghcr.io/x/y@sha256:0"}]),
        _wf([{"run": "gh release create v1"}]),
        _wf([{"run": "curl -X POST https://api.github.com/repos/x/y/releases"}]),
        _wf([{"run": "git push origin v1"}]),
        _wf([{"uses": "docker/login-action@0000000000000000000000000000000000000000"}]),
        _wf([{"uses": "docker/build-push-action@0000000000000000000000000000000000000000", "with": {"push": True}}]),
        _wf([{"uses": "./.github/actions/anything"}]),
        _wf([{"run": "echo ${{ secrets.GHCR_TOKEN }}"}]),
        _wf([{"run": "true"}], permissions={"packages": "write"}),
        _wf([{"run": "true"}], environment="release"),
        {
            "on": {"push": {}},
            "permissions": {"contents": "read"},
            "jobs": {"j": {"uses": "x/y/.github/workflows/z.yaml@main"}},
        },
        {"on": {"pull_request_target": {}}, "permissions": {"contents": "read"}, "jobs": {}},
        {"on": {"push": {}}, "permissions": "write-all", "jobs": {}},
        {"on": {"push": {}}, "jobs": {}},  # no permissions: the repository default, possibly write
    ],
)
def test_the_guard_catches_each_publishing_route(workflow):
    assert publishing_problems(workflow), workflow


def test_promotion_must_push_the_verified_archive():
    rebuild = {
        "permissions": {"contents": "read"},
        "jobs": {"publish": {"permissions": {"packages": "write"}, "steps": [{"run": "docker buildx build --push ."}]}},
    }
    assert len(promotion_problems(rebuild)) == 3
    promote = {
        "permissions": {"contents": "read"},
        "jobs": {
            "publish": {
                "permissions": {"packages": "write"},
                "environment": "release",
                "steps": [
                    {"run": "skopeo copy --all --preserve-digests oci-archive:candidate-1.tar docker://ghcr.io/x/y:1"},
                    {"run": "python tools/verify_image.py pulled.tar --version 1 --expect-digests digests.json"},
                ],
            }
        },
    }
    assert promotion_problems(promote) == []
