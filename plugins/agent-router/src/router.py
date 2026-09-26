#!/usr/bin/env python3
"""No-install entry point for the agent-router plugin.

Claude Code hooks run this script directly with any Python 3.8+ interpreter - it
puts the sibling ``src/`` directory on ``sys.path`` so the ``agent_router``
package resolves without the project being installed, then delegates to
``agent_router.cli``.

If the package *is* installed (uv / pip), the ``agent-router`` console script is
an equivalent entry point.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_router.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
