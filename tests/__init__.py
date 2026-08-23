"""Test and dev utilities. Run from repo root: python -m tests.test_pdf_export"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
