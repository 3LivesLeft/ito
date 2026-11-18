# SPDX-License-Identifier: Apache-2.0
"""Throwaway TLS certificate for the local status API (v0.2 security review).

Run as a short-lived process, so that the long-running core does not carry the `cryptography`
package (about 13 MB). A new key pair is made at every core start and never reused. Home Assistant
does not trust it through any authority: it pins the certificate's SHA-256 fingerprint, which
reaches it only in the Supervisor discovery message (readable only by Home Assistant Core).

    python -m meshbeacon.tlscert --dir <private directory>

writes ``key.pem`` and ``cert.pem`` (0600) and prints ``{"sha256": "<hex>"}``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path


def generate(directory: Path) -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MeshBeacon status")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=3650))  # pinned, not validated by date
        .sign(key, hashes.SHA256())
    )
    old = os.umask(0o077)
    try:
        (directory / "key.pem").write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        (directory / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    finally:
        os.umask(old)
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meshbeacon-tlscert")
    parser.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps({"sha256": generate(args.dir)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
