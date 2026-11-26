import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _real_inputs_to_tmp(tmp_path, monkeypatch):
    """Keep test uploads out of the user's Real_Inputs folder."""
    monkeypatch.setenv("TRINETRA_REAL_INPUTS_DIR", str(tmp_path / "Real_Inputs"))
