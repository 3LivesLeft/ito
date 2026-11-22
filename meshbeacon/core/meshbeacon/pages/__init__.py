# SPDX-License-Identifier: Apache-2.0
"""Nomad Network pages (v0.6.0, ADR 0027).

- ``store``: the hosted content, owned by the core (no RNS).
- ``helper`` and ``__main__``: the ``pages`` service, its own user ``mb-nomad``: browsing,
  discovery and the upstream ``nomadnet`` daemon as a child while the user hosts pages.
- ``nomadconfig``: the daemon's configuration, built with ConfigObj's object API.

The core never imports ``helper``; the helper never imports Home Assistant or HTTP-server code,
and nothing here imports ``nomadnet`` (it runs only as a separate program).
"""
