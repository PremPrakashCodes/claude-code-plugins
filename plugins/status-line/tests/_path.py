"""Make the `hud` package importable from the sibling `src/` directory.

Imported for its side effect at the top of every test module so the tests run
the same whether launched via ``unittest discover`` or as a single file.
"""

import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
