#!/usr/bin/env python3
from pathlib import Path
from typing import Dict

from lib import steamos_games_manifester as sgm
from lib import patcher
from lib import config_apps


def load_config_map(config_path: Path) -> Dict[str, str]:
    """Parse KEY=VALUE lines into a dict. Ignores comments and blanks."""
    config: Dict[str, str] = {}
    if not config_path.exists():
        return config
    for raw in config_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if key:
            config[key] = value
    return config


def main():
    script_dir = Path(__file__).resolve().parent
    cfg = load_config_map(script_dir / 'config.txt')

    # Execute steps with shared config map
    sgm.run(cfg)
    patcher.run(cfg)
    config_apps.run(cfg)


if __name__ == "__main__":
    main()