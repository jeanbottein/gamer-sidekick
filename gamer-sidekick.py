#!/usr/bin/env python3
from pathlib import Path
from typing import Dict
import logging

from lib import manifester 
from lib import patcher
from lib import configurer

logger = logging.getLogger(__name__)

def load_config_map(config_path: Path) -> Dict[str, str]:
    if not config_path.exists():
        return {}
    lines = (l.strip() for l in config_path.read_text().splitlines())
    pairs = (l.split('=', 1) for l in lines if l and not l.startswith('#') and '=' in l)
    config_map = {}
    for k, v in pairs:
        k = k.strip()
        if k:
            # Remove inline comments
            if '#' in v:
                v = v.split('#')[0]
            config_map[k] = v.strip()
    return config_map


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    script_dir = Path(__file__).resolve().parent
    cfg = load_config_map(script_dir / 'config.txt')

    manifester.run(cfg)
    patcher.run(cfg)
    configurer.run(cfg)


if __name__ == "__main__":
    main()