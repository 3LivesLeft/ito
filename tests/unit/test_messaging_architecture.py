# SPDX-License-Identifier: Apache-2.0
"""MS-21 (frontend independence) and the production boundary, checked on the source itself.

- The engine imports no Home Assistant, HTTP-server or UI code.
- Only ``messaging/engine.py`` imports LXMF; RNS only where the engine and its identity need it.
- The binding (``server.py``), the contract, the queue and the settings import neither.
- Nothing outside ``messaging/`` imports the engine or LXMF: the core, Reticulum and the Home
  Assistant integration run unchanged in production images, which do not contain it.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "meshbeacon" / "core" / "meshbeacon"
MESSAGING = CORE / "messaging"
INTEGRATION = REPO / "custom_components" / "meshbeacon"
FORBIDDEN_IN_ENGINE = ("homeassistant", "custom_components", "http.server", "aiohttp", "socketserver", "flask")


def imports(path: Path) -> set[str]:
    """Every module a file imports, at any depth (lazy imports inside functions included)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            found.add(base)
            found.update(f"{base}.{alias.name}" if node.module else f"{base}{alias.name}" for alias in node.names)
    return found


def top(names: set[str]) -> set[str]:
    return {n.split(".")[0] for n in names if not n.startswith(".")}


def test_the_engine_imports_no_home_assistant_http_server_or_ui_code():
    for path in MESSAGING.glob("*.py"):
        names = imports(path)
        bad = {n for n in names for f in FORBIDDEN_IN_ENGINE if n == f or n.startswith(f + ".")}
        assert not bad, (path.name, bad)


def test_only_the_engine_module_imports_lxmf():
    users = {p.name for p in MESSAGING.glob("*.py") if "LXMF" in top(imports(p))}
    assert users == {"engine.py"}


def test_the_binding_contract_queue_and_settings_import_neither_lxmf_nor_rns():
    for name in ("server.py", "contract.py", "queue.py", "settings.py"):
        assert not top(imports(MESSAGING / name)) & {"LXMF", "RNS"}, name


def test_nothing_outside_the_engine_imports_it_or_lxmf():
    for root in (CORE, INTEGRATION):
        for path in root.rglob("*.py"):
            if MESSAGING in path.parents:
                continue
            names = imports(path)
            assert "LXMF" not in top(names), path
            assert not any(".messaging" in n or n.startswith("meshbeacon.messaging") for n in names), path


def test_the_core_side_supervision_runs_only_when_the_option_is_on():
    """It is part of the core in every image (D-M4-8), but the core builds it only when the
    validated options switch messaging on and the messaging service exists."""
    text = (CORE / "supervisor.py").read_text()
    assert 'services.has("messaging")' in text
    assert "self.settings.messaging.enabled and self.engine is None and self.engine_factory is not None" in text
    assert "EngineSupervisor.enabled" not in text and "MARKER" not in text
