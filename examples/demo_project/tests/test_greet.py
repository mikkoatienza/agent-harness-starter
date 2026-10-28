import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from greet import greet  # noqa: E402


def test_greet_has_comma_and_bang() -> None:
    assert greet("Ada") == "Hello, Ada!"
