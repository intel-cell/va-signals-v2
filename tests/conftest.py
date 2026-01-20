import sys
from pathlib import Path

# Ensure project root is on sys.path so `import src` works when tests run from any CWD/import mode.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT_STR = str(PROJECT_ROOT)
if PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_STR)
