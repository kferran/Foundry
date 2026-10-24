"""The console's pytest fixtures. Helpers live in console_today_fixtures.py: the gate runs every extension's suite in
one pytest process, where `conftest` names whichever extension's conftest loaded last, so no test imports it by name."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console_today_fixtures import day, vault  # noqa: E402,F401  (pytest finds fixtures by name here)
