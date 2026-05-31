#!/usr/bin/env python3
"""No-install entry point for the status-line HUD.

Claude Code can run this script directly with any Python 3.8+ interpreter - it
puts the sibling ``src/`` directory on ``sys.path`` so the ``hud`` package
resolves without the project being installed, then delegates to ``hud.cli``.

If the package *is* installed (uv / pip), the ``status-line`` console script or
``python -m hud`` are equivalent, faster-resolving entry points.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hud.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
