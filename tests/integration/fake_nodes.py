# SPDX-License-Identifier: Apache-2.0
"""Misbehaving stand-ins for meshbeacon.node, used to test bounded recovery."""

import argparse
import os
import sys
import time


def _args():
    p = argparse.ArgumentParser()
    p.add_argument("--config")
    p.add_argument("--status-fd", type=int)
    p.add_argument("--interval", type=float)
    p.add_argument("--parent", type=int)
    return p.parse_args()


def crash() -> None:
    _args()
    print("fake node: crashing on purpose", flush=True)
    sys.exit(3)


def hang() -> None:
    _args()
    time.sleep(3600)


def hog() -> None:
    a = _args()
    blob = bytearray(300 * 1024 * 1024)
    for i in range(0, len(blob), 4096):
        blob[i] = 1
    f = os.fdopen(a.status_fd, "w", buffering=1)
    while True:
        f.write('{"interfaces": []}\n')
        time.sleep(0.5)


if __name__ == "__main__":
    {"crash": crash, "hang": hang, "hog": hog}[os.environ.get("FAKE_NODE", "crash")]()
