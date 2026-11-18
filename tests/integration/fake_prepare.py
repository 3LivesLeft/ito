# SPDX-License-Identifier: Apache-2.0
"""A deliberately slow stand-in for meshbeacon.prepare (PR #2 review, item 2)."""

import os
import sys
import time

from meshbeacon import prepare

if __name__ == "__main__":
    time.sleep(float(os.environ.get("FAKE_PREPARE_SLEEP", "5")))
    sys.exit(prepare.main())
