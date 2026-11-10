"""Locations shared by the replication scripts."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
P = Path(os.environ.get("AUDIT_RESULTS_DIR", ROOT / "results")).resolve()
FIGURES = ROOT / "outputs" / "figures"
