# SPDX-License-Identifier: Apache-2.0
"""tools/verify_image.py on synthetic OCI archives shaped like `docker buildx` output (M1, D3)."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import verify_image  # noqa: E402 - after the path is set

PROJECT = yaml.safe_load((ROOT / "project.yaml").read_text())


def labels(version: str = "0.3.0") -> dict[str, str]:
    return {
        "io.hass.type": "app",
        "io.hass.version": version,
        "org.opencontainers.image.source": PROJECT["repository"],
        "org.opencontainers.image.title": PROJECT["name"],
        "org.opencontainers.image.licenses": "Apache-2.0 AND LicenseRef-Reticulum",
    }


def build_archive(
    path: Path,
    *,
    platforms=("amd64", "arm64"),
    version="0.3.0",
    layer_seed="same",
    sbom=True,
    provenance=True,
    when="t1",
    nested=True,
) -> Path:
    blobs: dict[str, bytes] = {}

    def put(obj: object) -> dict[str, object]:
        data = json.dumps(obj, sort_keys=True).encode()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        blobs[digest] = data
        return {"digest": digest, "size": len(data)}

    entries = []
    for arch in platforms:
        config = put({"config": {"Labels": labels(version)}, "architecture": arch})
        layer = put({"layer": f"{layer_seed}-{arch}"})
        manifest = put({"schemaVersion": 2, "config": config, "layers": [layer]})
        entries.append(
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                **manifest,
                "platform": {"os": "linux", "architecture": arch},
            }
        )
        layers = []
        if sbom:
            layers.append({**put({"sbom": arch}), "annotations": {"in-toto.io/predicate-type": verify_image.SPDX}})
        if provenance:
            layers.append(
                {
                    **put({"built": when, "arch": arch}),
                    "annotations": {"in-toto.io/predicate-type": "https://slsa.dev/provenance/v1"},
                }
            )
        attestation = put({"schemaVersion": 2, "layers": layers})
        entries.append(
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                **attestation,
                "platform": {"os": "unknown", "architecture": "unknown"},
                "annotations": {
                    "vnd.docker.reference.type": "attestation-manifest",
                    "vnd.docker.reference.digest": manifest["digest"],
                },
            }
        )
    if nested:
        index = put({"schemaVersion": 2, "manifests": entries})
        top = {"schemaVersion": 2, "manifests": [{"mediaType": "application/vnd.oci.image.index.v1+json", **index}]}
    else:
        top = {"schemaVersion": 2, "manifests": entries}
    with tarfile.open(path, "w") as tar:

        def add(name: str, data: bytes) -> None:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

        add("index.json", json.dumps(top).encode())
        add("oci-layout", b'{"imageLayoutVersion": "1.0.0"}')
        for digest, data in blobs.items():
            add(f"blobs/sha256/{digest.split(':')[1]}", data)
    return path


def test_two_identical_builds_pass_and_report_digests(tmp_path, capsys):
    one = build_archive(tmp_path / "1.tar", when="t1")
    two = build_archive(tmp_path / "2.tar", when="t2")  # attestations differ by time; images do not
    summary = tmp_path / "summary.md"
    assert verify_image.main([str(one), str(two), "--version", "0.3.0", "--summary", str(summary)]) == 0
    out = capsys.readouterr().out
    assert "linux/amd64" in out and "linux/arm64" in out and "reproducible: yes" in out
    assert "sha256:" in summary.read_text()


def test_a_flat_index_is_read_too(tmp_path):
    assert verify_image.main([str(build_archive(tmp_path / "1.tar", nested=False)), "--version", "0.3.0"]) == 0


def test_different_builds_are_not_reproducible(tmp_path, capsys):
    one = build_archive(tmp_path / "1.tar")
    two = build_archive(tmp_path / "2.tar", layer_seed="other")
    assert verify_image.main([str(one), str(two), "--version", "0.3.0"]) == 1
    out = capsys.readouterr().out
    assert "not reproducible" in out and "layer 0 differs" in out  # says where


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"platforms": ("amd64",)}, "platforms"),
        ({"version": "0.2.0"}, "io.hass.version"),
        ({"sbom": False}, "SBOM"),
        ({"provenance": False}, "provenance"),
    ],
)
def test_missing_pieces_are_reported(tmp_path, capsys, kwargs, expected):
    archive = build_archive(tmp_path / "1.tar", **kwargs)
    assert verify_image.main([str(archive), "--version", "0.3.0"]) == 1
    assert expected in capsys.readouterr().out


def test_a_tampered_blob_is_caught(tmp_path):
    good = build_archive(tmp_path / "1.tar")
    bad = tmp_path / "bad.tar"
    with tarfile.open(good) as src, tarfile.open(bad, "w") as dst:
        for member in src.getmembers():
            data = src.extractfile(member).read()
            if member.name.startswith("blobs/") and b'"Labels"' in data:
                data = data.replace(b"Apache-2.0", b"Proprietary")
            member.size = len(data)
            dst.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError, match="does not match"):
        verify_image.main([str(bad), "--version", "0.3.0"])


def test_explain_names_the_files_that_differ(tmp_path):
    """With real tar layers, the explanation lists the differing files (for CI diagnosis)."""

    def tar_layer(content: bytes, mtime: int) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as layer:
            info = tarfile.TarInfo("lib/apk/db/installed")
            info.size, info.mtime = len(content), mtime
            layer.addfile(info, io.BytesIO(content))
            same = tarfile.TarInfo("etc/same")
            same.size = 1
            layer.addfile(same, io.BytesIO(b"x"))
        return buf.getvalue()

    def archive(path: Path, layer: bytes) -> verify_image.Archive:
        digest = "sha256:" + hashlib.sha256(layer).hexdigest()
        config = json.dumps({"config": {"Labels": {}}}).encode()
        cdigest = "sha256:" + hashlib.sha256(config).hexdigest()
        manifest = json.dumps({"config": {"digest": cdigest}, "layers": [{"digest": digest}]}).encode()
        mdigest = "sha256:" + hashlib.sha256(manifest).hexdigest()
        with tarfile.open(path, "w") as tar:
            for d, data in ((digest, layer), (cdigest, config), (mdigest, manifest)):
                info = tarfile.TarInfo(f"blobs/sha256/{d.split(':')[1]}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return verify_image.Archive(path), mdigest

    first, d1 = archive(tmp_path / "a.tar", tar_layer(b"one", 1))
    second, d2 = archive(tmp_path / "b.tar", tar_layer(b"two", 2))
    try:
        lines = verify_image.explain(first, second, {"linux/amd64": d1}, {"linux/amd64": d2})
    finally:
        first.close()
        second.close()
    assert any("layer 0 differs in 1 entries" in line for line in lines)
    assert any("lib/apk/db/installed" in line for line in lines)
    assert not any("etc/same" in line for line in lines)


def test_the_verified_digests_are_recorded_and_promotion_is_checked(tmp_path):
    """M1.2: publishing pushes the verified archive; the complete image served afterwards (index,
    platform manifests and attestations) must match the record exactly."""
    one = build_archive(tmp_path / "1.tar", when="t1")
    two = build_archive(tmp_path / "2.tar", when="t2")
    record = tmp_path / "digests.json"
    assert verify_image.main([str(one), str(two), "--version", "0.3.0", "--write-digests", str(record)]) == 0
    saved = json.loads(record.read_text())
    assert saved["version"] == "0.3.0" and saved["index"].startswith("sha256:")
    assert set(saved["platforms"]) == set(saved["attestations"]) == {"linux/amd64", "linux/arm64"}
    # The very same archive, as a registry serves it back after promotion: accepted.
    promoted = tmp_path / "promoted.tar"
    promoted.write_bytes(one.read_bytes())
    assert verify_image.main([str(promoted), "--version", "0.3.0", "--expect-digests", str(record)]) == 0
    # Same image layers, but different attestations (for example a substituted SBOM): refused.
    reattested = build_archive(tmp_path / "3.tar", when="t3")
    assert verify_image.main([str(reattested), "--version", "0.3.0", "--expect-digests", str(record)]) == 1
    # A rebuild that differs, or a record for another version: refused.
    other = build_archive(tmp_path / "4.tar", layer_seed="rebuilt")
    assert verify_image.main([str(other), "--version", "0.3.0", "--expect-digests", str(record)]) == 1
    assert verify_image.main([str(promoted), "--version", "0.3.1", "--expect-digests", str(record)]) == 1


def test_an_incomplete_record_is_refused(tmp_path):
    one = build_archive(tmp_path / "1.tar")
    record = tmp_path / "digests.json"
    assert verify_image.main([str(one), "--version", "0.3.0", "--write-digests", str(record)]) == 0
    saved = json.loads(record.read_text())
    del saved["attestations"]  # an old-style record: platforms only
    record.write_text(json.dumps(saved))
    assert verify_image.main([str(one), "--version", "0.3.0", "--expect-digests", str(record)]) == 1


def test_a_flat_layout_records_its_index_too(tmp_path):
    flat = build_archive(tmp_path / "flat.tar", nested=False)
    record = tmp_path / "digests.json"
    assert verify_image.main([str(flat), "--version", "0.3.0", "--write-digests", str(record)]) == 0
    assert json.loads(record.read_text())["index"].startswith("sha256:")


def test_no_record_is_written_for_a_failing_candidate(tmp_path):
    one = build_archive(tmp_path / "1.tar")
    other = build_archive(tmp_path / "2.tar", layer_seed="different")
    record = tmp_path / "digests.json"
    assert verify_image.main([str(one), str(other), "--version", "0.3.0", "--write-digests", str(record)]) == 1
    assert not record.exists()
