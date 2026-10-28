"""A deterministic stand-in for a coding agent.

Real setups point the harness at a CLI agent instead. This script reads the
spec from $HARNESS_SPEC and makes a fixed edit, so the demo runs offline.
On its first attempt it makes a deliberately incomplete edit to show the
retry-with-feedback loop.
"""

import os
from pathlib import Path

spec = Path(os.environ["HARNESS_SPEC"]).read_text()
target = Path("src/greet.py")
if "Feedback from previous attempt" in spec:
    target.write_text('def greet(name: str) -> str:\n    return f"Hello, {name}!"\n')
else:
    target.write_text('def greet(name: str) -> str:\n    return f"Hello, {name}"\n')
print("HARNESS_TOKENS=0")
