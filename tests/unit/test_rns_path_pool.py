# SPDX-License-Identifier: Apache-2.0
"""Pin canary for docs/research/known-paths.md and the panel's "Known paths" note.

Reads one public class constant of the pinned RNS; nothing is started or patched. If an RNS upgrade
changes it, update the document, ``PATH_POOL_TARGET`` in the panel's model.js and this test together.
"""

import re
from pathlib import Path

import RNS

MODEL = Path(__file__).resolve().parents[2] / "custom_components" / "meshbeacon" / "frontend" / "model.js"


def test_unused_path_pool_target_is_what_the_docs_and_panel_say():
    assert RNS.Transport.PATH_POOL_UNUSED_TARGET == 2048
    panel = re.search(r"PATH_POOL_TARGET = (\d+);", MODEL.read_text())
    assert panel is not None
    assert int(panel.group(1)) == RNS.Transport.PATH_POOL_UNUSED_TARGET
