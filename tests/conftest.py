import sys
from pathlib import Path

# Discover yarns from sibling repo (../textile-yarns/yarns) or fallback to workspace
sibling_yarns = Path(__file__).resolve().parents[2] / "textile-yarns" / "yarns"
local_yarns = Path(__file__).resolve().parents[1] / "yarns"
YARNS_DIR = sibling_yarns if sibling_yarns.exists() else local_yarns

if YARNS_DIR.exists() and str(YARNS_DIR) not in sys.path:
    sys.path.insert(0, str(YARNS_DIR))
