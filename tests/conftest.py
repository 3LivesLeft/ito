# SPDX-License-Identifier: Apache-2.0
"""Root test configuration.

The Home Assistant integration tests (tests/ha) need Home Assistant and its test harness, which
require a newer Python than the app image. They run in their own CI job; elsewhere they are not
collected.
"""

import importlib.util

collect_ignore = [] if importlib.util.find_spec("pytest_homeassistant_custom_component") else ["ha"]
