# SPDX-License-Identifier: Apache-2.0
"""Verify a release candidate image, offline, from OCI archives made by ``docker buildx``.

    python tools/verify_image.py build1.tar [build2.tar] --version 0.3.0 [--summary out.md]

Checks, for the multi-arch image the Supervisor will pull (decision D3):

- both platforms are present (linux/amd64 and linux/arm64, the app's ``amd64`` and ``aarch64``);
- each image carries the labels the Supervisor and users rely on (``io.hass.type=app``,
  ``io.hass.version``, the source repository, the licence);
- each platform has an SBOM attestation (SPDX) and a provenance attestation;
- **reproducibility:** with a second archive from an independent build of the same commit, every
  platform's image manifest digest is identical (attestations carry timestamps and are excluded).

It prints the digests to record in the release notes. Nothing is pushed, signed or published:
that is M2's publishing step, after approval (docs/releasing.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = yaml.safe_load((ROOT / "project.yaml").read_text())
PLATFORMS = {"linux/amd64", "linux/arm64"}
INDEX_TYPES = {"application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json"}
ATTESTATION = "attestation-manifest"
SPDX = "https://spdx.dev/Document"


class Archive:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._tar = tarfile.open(path)  # noqa: SIM115 - closed in close()

    def close(self) -> None:
        self._tar.close()

    def json(self, name: str) -> Any:
        member = self._tar.extractfile(name)
        if member is None:
            raise ValueError(f"{name} missing")
        return json.loads(member.read())

    def blob(self, digest: str) -> Any:
        algorithm, value = digest.split(":", 1)
        member = self._tar.extractfile(f"blobs/{algorithm}/{value}")
        if member is None:
            raise ValueError(f"blob {digest} missing")
        data = member.read()
        if hashlib.sha256(data).hexdigest() != value:
            raise ValueError(f"blob {digest} does not match its digest")
        return json.loads(data)

    def descriptors(self) -> list[dict[str, Any]]:
        """Platform and attestation manifests, following one level of image index."""
        found: list[dict[str, Any]] = []
        for descriptor in self.json("index.json")["manifests"]:
            if descriptor.get("mediaType") in INDEX_TYPES:
                found += self.blob(descriptor["digest"])["manifests"]
            else:
                found.append(descriptor)
        return found


def platform_of(descriptor: dict[str, Any]) -> str:
    platform = descriptor.get("platform") or {}
    return f"{platform.get('os')}/{platform.get('architecture')}"


def inspect(archive: Archive, version: str) -> tuple[dict[str, str], list[str]]:
    """(platform → image manifest digest, problems)."""
    problems: list[str] = []
    descriptors = archive.descriptors()
    images = {
        platform_of(d): d
        for d in descriptors
        if (d.get("annotations") or {}).get("vnd.docker.reference.type") != ATTESTATION
    }
    attestations = {
        (d.get("annotations") or {}).get("vnd.docker.reference.digest"): d
        for d in descriptors
        if (d.get("annotations") or {}).get("vnd.docker.reference.type") == ATTESTATION
    }
    if set(images) != PLATFORMS:
        problems.append(f"platforms {sorted(images)}, expected {sorted(PLATFORMS)}")
    for platform, descriptor in sorted(images.items()):
        manifest = archive.blob(descriptor["digest"])
        labels = (archive.blob(manifest["config"]["digest"]).get("config") or {}).get("Labels") or {}
        expected = {
            "io.hass.type": "app",
            "io.hass.version": version,
            "org.opencontainers.image.source": PROJECT["repository"],
            "org.opencontainers.image.title": PROJECT["name"],
        }
        for key, value in expected.items():
            if labels.get(key) != value:
                problems.append(f"{platform}: label {key}={labels.get(key)!r}, expected {value!r}")
        if not str(labels.get("org.opencontainers.image.licenses", "")).startswith("Apache-2.0"):
            problems.append(f"{platform}: licence label missing")
        attestation = attestations.get(descriptor["digest"])
        if attestation is None:
            problems.append(f"{platform}: no attestations (SBOM and provenance)")
            continue
        predicates = {
            (layer.get("annotations") or {}).get("in-toto.io/predicate-type", "")
            for layer in archive.blob(attestation["digest"]).get("layers", [])
        }
        if SPDX not in predicates:
            problems.append(f"{platform}: no SPDX SBOM attestation")
        if not any("slsa.dev/provenance" in p for p in predicates):
            problems.append(f"{platform}: no provenance attestation")
    return {p: d["digest"] for p, d in images.items()}, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--summary", type=Path, help="write a Markdown summary (for example the CI job summary)")
    args = parser.parse_args(argv)
    if len(args.archives) > 2:
        parser.error("one archive, or two independent builds to compare")
    results = []
    problems: list[str] = []
    for path in args.archives:
        archive = Archive(path)
        try:
            digests, found = inspect(archive, args.version)
        finally:
            archive.close()
        results.append(digests)
        problems += [f"{path.name}: {p}" for p in found]
    if len(results) == 2 and results[0] != results[1]:
        problems.append(f"not reproducible: {results[0]} != {results[1]}")
    lines = [f"### {PROJECT['name']} {args.version}: image manifest digests", ""]
    lines += [f"- `{platform}`: `{digest}`" for platform, digest in sorted(results[0].items())]
    if len(results) == 2:
        lines.append(f"- reproducible: {'yes' if results[0] == results[1] else 'NO'}")
    lines += [f"- ✖ {p}" for p in problems]
    print("\n".join(lines))
    if args.summary:
        with args.summary.open("a") as summary:
            summary.write("\n".join(lines) + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
