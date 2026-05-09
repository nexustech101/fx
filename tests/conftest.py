from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FRAMEWORK = ROOT.parent
REGISTERS_SRC = FRAMEWORK / "registers" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(REGISTERS_SRC) not in sys.path:
    sys.path.insert(0, str(REGISTERS_SRC))
