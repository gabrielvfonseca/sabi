"""Root entry point for the sabi project.

Allows running the project directory directly:

    python /path/to/sabi-extrator --search "madrid software"

Equivalent to `python -m src.cli` or the `sabi` console script.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable so `src` resolves when run from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
