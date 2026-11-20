# SPDX-License-Identifier: Apache-2.0
"""The standalone LXMF messaging engine (M4; ADR 0008, 0009, 0011, 0014, 0018).

It runs as its own process and Unix user (``mb-lxmf``), off by default and absent from production
images. It knows nothing of Home Assistant: other parts of MeshBeacon reach it only through the
Messaging Service contract v1 (``contract``), carried by a binding (``server``).

Only ``engine`` and ``msgidentity`` import RNS and LXMF, and only through their public APIs.
"""
