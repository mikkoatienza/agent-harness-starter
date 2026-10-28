from __future__ import annotations

import shutil
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    shutil.copytree(EXAMPLES / "demo_project", tmp_path / "demo_project")
    shutil.copytree(EXAMPLES / "agents", tmp_path / "agents")
    return tmp_path / "demo_project"
