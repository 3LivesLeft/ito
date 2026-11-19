# SPDX-License-Identifier: Apache-2.0
"""Verify a release candidate image, offline, from OCI archives made by ``docker buildx``.

    python tools/verify_image.py build1.tar [build2.tar] --version 0.3.0 [--summary out.md]
        [--write-digests digests.json] [--expect-digests digests.json]

Checks, for the multi-arch image the Supervisor will pull (decision D3):

- both platforms are present (linux/amd64 and linux/arm64, the app's ``amd64`` and ``aarch64``);
- each image carries the labels the Supervisor and users rely on (``io.hass.type=app``,
  ``io.hass.version``, the source repository, the licence);
- each platform has an SBOM attestation (SPDX) and a provenance attestation;
- **reproducibility:** with a second archive from an independent build of the same commit, every
  platform's image manifest digest is identical (attestations carry timestamps and are excluded).

It prints the digests to record in the release notes, and ``--write-digests`` records them. The
**promotion rule** (M1.2, docs/releasing.md step 4): publishing pushes the verified archive
itself, never a rebuild, and the image pulled back from the registry must pass
``--expect-digests`` against that record. Nothing is pushed, signed or published here: that is
M2's publishing step, after approval.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
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

    def raw(self, digest: str) -> bytes:
        algorithm, value = digest.split(":", 1)
        member = self._tar.extractfile(f"blobs/{algorithm}/{value}")
        if member is None:
            raise ValueError(f"blob {digest} missing")
        data = member.read()
        if hashlib.sha256(data).hexdigest() != value:
            raise ValueError(f"blob {digest} does not match its digest")
        return data

    def blob(self, digest: str) -> Any:
        return json.loads(self.raw(digest))

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


def _layer_entries(archive: Archive, digest: str) -> dict[str, tuple[object, ...]]:
    data = archive.raw(digest)
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    entries: dict[str, tuple[object, ...]] = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as layer:
        for member in layer.getmembers():
            content = layer.extractfile(member) if member.isfile() else None
            digest_ = hashlib.sha256(content.read()).hexdigest()[:16] if content else ""
            entries[member.name] = (digest_, member.mtime, member.mode, member.uid, member.gid, member.linkname)
    return entries


def explain(first: Archive, second: Archive, a: dict[str, str], b: dict[str, str], limit: int = 15) -> list[str]:
    """Which layers and files differ between two builds, to find what is not reproducible."""
    lines: list[str] = []
    for platform in sorted(set(a) & set(b)):
        if a[platform] == b[platform]:
            continue
        one, two = first.blob(a[platform]), second.blob(b[platform])
        c1, c2 = first.blob(one["config"]["digest"]), second.blob(two["config"]["digest"])
        lines += [
            f"{platform}: config field {key!r} differs"
            for key in sorted(set(c1) | set(c2))
            if key != "rootfs" and c1.get(key) != c2.get(key)
        ]
        for index, (l1, l2) in enumerate(zip(one["layers"], two["layers"], strict=False)):
            if l1["digest"] == l2["digest"]:
                continue
            try:
                e1, e2 = _layer_entries(first, l1["digest"]), _layer_entries(second, l2["digest"])
            except (tarfile.TarError, OSError, EOFError):
                lines.append(f"{platform}: layer {index} differs (not a readable tar layer)")
                continue
            changed = sorted(name for name in set(e1) | set(e2) if e1.get(name) != e2.get(name))
            lines.append(f"{platform}: layer {index} differs in {len(changed)} entries")
            for name in changed[:limit]:
                lines.append(f"    {name}: {e1.get(name)} != {e2.get(name)}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--summary", type=Path, help="write a Markdown summary (for example the CI job summary)")
    parser.add_argument("--write-digests", type=Path, help="record the verified digests (JSON) for promotion")
    parser.add_argument("--expect-digests", type=Path, help="fail unless the digests equal this record")
    args = parser.parse_args(argv)
    if len(args.archives) > 2:
        parser.error("one archive, or two independent builds to compare")
    results = []
    problems: list[str] = []
    archives = [Archive(path) for path in args.archives]
    try:
        for path, archive in zip(args.archives, archives, strict=True):
            digests, found = inspect(archive, args.version)
            results.append(digests)
            problems += [f"{path.name}: {p}" for p in found]
        if len(results) == 2 and results[0] != results[1]:
            problems.append(f"not reproducible: {results[0]} != {results[1]}")
            for line in explain(archives[0], archives[1], results[0], results[1]):
                print(line)
    finally:
        for archive in archives:
            archive.close()
    if args.expect_digests is not None:
        expected = json.loads(args.expect_digests.read_text())
        if expected.get("version") != args.version:
            problems.append(f"digest record is for version {expected.get('version')!r}, not {args.version!r}")
        if expected.get("platforms") != results[0]:
            problems.append(f"not the verified image: {results[0]} != {expected.get('platforms')}")
    if args.write_digests is not None and not problems:
        record = {"version": args.version, "platforms": dict(sorted(results[0].items()))}
        args.write_digests.write_text(json.dumps(record, indent=2) + "\n")
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
