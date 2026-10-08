import sys
from collections.abc import Generator
from pathlib import Path

import pytest

from textile.core.orchestration.skein import skein

# Discover yarns from sibling repo (../textile-yarns/yarns) or fallback to workspace
sibling_yarns = Path(__file__).resolve().parents[2] / "textile-yarns" / "yarns"
local_yarns = Path(__file__).resolve().parents[1] / "yarns"
YARNS_DIR = sibling_yarns if sibling_yarns.exists() else local_yarns

if YARNS_DIR.exists() and str(YARNS_DIR) not in sys.path:
    sys.path.insert(0, str(YARNS_DIR))


@pytest.fixture(autouse=True)
def isolate_skein_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Ensure tests run with an isolated config and settings directory, avoiding live ~/.config pollution."""
    test_config_dir = tmp_path / ".config" / "textile"
    test_config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TEXTILE_CONFIG_DIR", str(test_config_dir))

    orig_config_dir = skein._config_dir
    orig_config_file = skein._config_file
    orig_settings_file = skein._settings_file
    orig_settings = skein._settings.copy()

    skein._config_dir = test_config_dir
    skein._config_file = test_config_dir / "config.json"
    skein._settings_file = test_config_dir / "settings.toml"

    yield

    skein._config_dir = orig_config_dir
    skein._config_file = orig_config_file
    skein._settings_file = orig_settings_file
    skein._settings = orig_settings
