"""Import paths for the handoffs extension's tests: the extension's own scripts, then the vault's system/scripts
(vaultlib). The tests run from a vault whose extensions/handoffs/ is this folder's grandparent."""
import sys
from pathlib import Path

EXT = Path(__file__).resolve().parents[2]
VAULT = EXT.parents[1]
sys.path[:0] = [str(EXT / "scripts"), str(VAULT / "system" / "scripts")]
