#!/usr/bin/env python3
from pathlib import Path
from typing import Dict
import logging

from lib import manifester 
from lib import patcher
from lib import configurer

logger = logging.getLogger(__name__)

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
    # Centralized logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    script_dir = Path(__file__).resolve().parent
    cfg = load_config_map(script_dir / 'config.txt')

    # Execute steps with shared config map
    manifester.run(cfg)
    patcher.run(cfg)
    configurer.run(cfg)


if __name__ == "__main__":
    main()