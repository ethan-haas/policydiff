"""Ensures the `policydiff` package (living at the repo root next to this
file) is importable when pytest is invoked from workspace/policydiff-ins/.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
