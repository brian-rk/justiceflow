import sys
from pathlib import Path

# The ML core lives at the repo root as the `justiceflow` package.
_root = str(Path(__file__).resolve().parents[2])
if _root not in sys.path:
    sys.path.insert(0, _root)
