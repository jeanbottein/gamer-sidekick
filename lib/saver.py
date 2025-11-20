import os
import json
import logging
import shutil
import re

from . import manifester

logger = logging.getLogger("saver")


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def _resolve_base_path(path: str) -> str:
    path = os.path.expandvars(os.path.expanduser(path))
    return os.path.abspath(path)


def _resolve_save_path(save_path: str, manifest_path: str) -> str:
    if not save_path:
        return ""
    save_path = os.path.expandvars(os.path.expanduser(save_path))
    if not os.path.isabs(save_path):
        manifest_dir = os.path.dirname(manifest_path)
        save_path = os.path.join(manifest_dir, save_path)
    return os.path.normpath(save_path)


def _sanitize_title(title: str) -> str:
    if not title:
        title = "game"
    name = title.strip()
    name = "".join(
        c if c not in '<>:"/\\|?*' and ord(c) >= 32 else "_" for c in name
    )
    name = re.sub(r"\s+", "_", name)
    name = name.rstrip(". ")
    if not name:
        name = "game"
    upper = name.upper()
    if upper in WINDOWS_RESERVED_NAMES:
        name = f"{name}_game"
    if len(name) > 100:
        name = name[:100]
    return name


def _build_file_map(root: str) -> dict:
    files = {}
    if not os.path.isdir(root):
        return files
    for dirpath, dirnames, filenames in os.walk(root):
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, root)
            files[rel] = full
    return files


def _copy_file(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        shutil.copy2(src, dst)
    except Exception as e:
        logger.error(f"❌ Error copying {src} -> {dst}: {e}")


def _bisync_dirs(a_root: str, b_root: str) -> None:
    a_files = _build_file_map(a_root)
    b_files = _build_file_map(b_root)

    all_rel = set(a_files) | set(b_files)
    for rel in sorted(all_rel):
        a_path = a_files.get(rel)
        b_path = b_files.get(rel)

        if a_path and not b_path:
            _copy_file(a_path, os.path.join(b_root, rel))
            continue
        if b_path and not a_path:
            _copy_file(b_path, os.path.join(a_root, rel))
            continue

        if not a_path or not b_path:
            continue

        try:
            a_mtime = os.path.getmtime(a_path)
            b_mtime = os.path.getmtime(b_path)
        except OSError as e:
            logger.error(f"❌ Error getting mtime for {rel}: {e}")
            continue

        if a_mtime > b_mtime + 1e-6:
            _copy_file(a_path, b_path)
        elif b_mtime > a_mtime + 1e-6:
            _copy_file(b_path, a_path)


def _sync_one_manifest(manifest_path: str, saves_root: str) -> None:
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    except Exception as e:
        logger.error(f"❌ Error reading manifest {manifest_path}: {e}")
        return

    title = manifest.get("title") or os.path.basename(os.path.dirname(manifest_path))
    save_path = manifest.get("savePath", "")
    if not save_path:
        logger.info(f"ℹ️ {title}: no savePath defined, skipping")
        return

    src_dir = _resolve_save_path(save_path, manifest_path)
    dst_dir = os.path.join(saves_root, _sanitize_title(title))

    if not os.path.isdir(src_dir) and not os.path.isdir(dst_dir):
        logger.info(f"ℹ️ {title}: no save directory on either side, skipping")
        return

    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(dst_dir, exist_ok=True)

    logger.info(f"🤖 Syncing saves for {title}")
    _bisync_dirs(src_dir, dst_dir)
    logger.info(f"✅ {title}: saves synchronized")


def run(config: dict) -> None:
    games_dir = config.get("FREEGAMES_PATH")
    saves_root = config.get("SAVESCOPY_PATH")

    if not games_dir or not os.path.isdir(games_dir):
        logger.warning("🤖 FREEGAMES_PATH not configured or invalid")
        return

    if not saves_root:
        logger.warning("🤖 SAVESCOPY_PATH not configured")
        return

    saves_root = _resolve_base_path(saves_root)
    os.makedirs(saves_root, exist_ok=True)

    manifests = manifester.find_manifests(games_dir)
    if not manifests:
        logger.info("🤖 No launch_manifest.json found, nothing to sync")
        return

    logger.info(f"🤖 Syncing saves to {saves_root}")
    for manifest_path in manifests:
        _sync_one_manifest(manifest_path, saves_root)
