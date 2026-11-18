# SPDX-License-Identifier: Apache-2.0
"""MeshBeacon core: runs and supervises the unmodified Reticulum reference implementation.

The core has no Home Assistant dependencies. Only :mod:`meshbeacon.prepare` and
:mod:`meshbeacon.node` import RNS, and both run as separate, short-lived or child processes so
that the long-running supervisor stays small.
"""

__version__ = "0.1.2"
