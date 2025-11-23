#!/usr/bin/env python3
from pathlib import Path
from typing import Dict
import logging
import shutil

from lib import manifester
from lib import patcher
from lib import configurer
from lib import saver

logger = logging.getLogger(__name__)

def load_config_map(config_path: Path) -> Dict[str, str]:
    if not config_path.exists():
        logger.warning(f"⚠️ Config file {config_path} not found; continuing with empty configuration")
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


def ensure_config_file(script_dir: Path) -> Path:
    config_path = script_dir / 'config.txt'
    default_path = script_dir / 'config-default.txt'

    if config_path.exists():
        logger.info(f"📄 Loaded config from {config_path}")
        return config_path

    if default_path.exists():
        try:
            shutil.copy2(default_path, config_path)
            logger.info(
                f"🆕 config.txt missing. Copied defaults from {default_path.name} and loaded configuration"
            )
        except OSError as exc:
            logger.error(f"❌ Failed to copy {default_path} -> {config_path}: {exc}")
    else:
        logger.warning("⚠️ config.txt missing and config-default.txt not found. Using empty configuration")

    return config_path


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    script_dir = Path(__file__).resolve().parent
    config_path = ensure_config_file(script_dir)
    cfg = load_config_map(config_path)

    manifester.run(cfg)
    saver.run(cfg)
    patcher.run(cfg)
    configurer.run(cfg)


if __name__ == "__main__":
    main()