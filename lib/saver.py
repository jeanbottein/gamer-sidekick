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


SYNC_META_NAME = ".gamer-sidekick"


def _max_mtime(files: dict) -> float:
    if not files:
        return 0.0
    try:
        return max(os.path.getmtime(p) for p in files.values())
    except OSError as e:
        logger.error(f"❌ Error computing directory mtime snapshot: {e}")
        return 0.0


def _read_sync_meta(root: str):
    meta_path = os.path.join(root, SYNC_META_NAME)
    if not os.path.isfile(meta_path):
        return None
    try:
        with open(meta_path, "r") as f:
            data = json.load(f)
        return float(data.get("last_snapshot_mtime", 0.0))
    except Exception as e:
        logger.error(f"❌ Error reading sync metadata {meta_path}: {e}")
        return None


def _write_sync_meta(root: str, snapshot_mtime: float) -> None:
    if not os.path.isdir(root):
        return
    meta_path = os.path.join(root, SYNC_META_NAME)
    payload = {"last_snapshot_mtime": float(snapshot_mtime)}
    try:
        with open(meta_path, "w") as f:
            json.dump(payload, f)
    except Exception as e:
        logger.error(f"❌ Error writing sync metadata {meta_path}: {e}")


def _copy_file(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        if os.path.exists(dst):
            try:
                src_stat = os.stat(src)
                dst_stat = os.stat(dst)
            except OSError:
                # If we can't stat, fall back to copying
                shutil.copy2(src, dst)
                return

            # If destination is at least as new and same size, treat as identical
            if (
                src_stat.st_size == dst_stat.st_size
                and src_stat.st_mtime <= dst_stat.st_mtime
            ):
                return

        shutil.copy2(src, dst)
    except Exception as e:
        logger.error(f"❌ Error copying {src} -> {dst}: {e}")


def _copy_tree_one_way(src_root: str, dst_root: str) -> None:
    files = _build_file_map(src_root)
    if not files:
        return
    for rel, src_path in files.items():
        dst_path = os.path.join(dst_root, rel)
        _copy_file(src_path, dst_path)


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


def _sync_one_manifest(manifest_path: str, saves_root: str, strategy: str) -> None:
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    except Exception as e:
        logger.error(f"❌ Error reading manifest {manifest_path}: {e}")
        return

    title = manifest.get("title") or os.path.basename(os.path.dirname(manifest_path))
    raw_save = manifest.get("savePath", "")
    try:
        if hasattr(manifester, "_pick_save_path"):
            save_path = manifester._pick_save_path(raw_save)
        else:
            save_path = raw_save
    except Exception as e:
        logger.error(f"❌ {title}: error resolving savePath {raw_save!r}: {e}")
        return

    if not save_path:
        logger.info(f"ℹ️ {title}: no savePath defined, skipping")
        return

    src_dir = _resolve_save_path(save_path, manifest_path)
    dst_dir = os.path.join(saves_root, _sanitize_title(title))

    if strategy == "backup":
        if not os.path.isdir(src_dir):
            logger.info(f"ℹ️ {title}: source save directory {src_dir} not found, skipping backup")
            return
        src_files = _build_file_map(src_dir)
        if not src_files:
            logger.info(f"ℹ️ {title}: source save directory {src_dir} is empty, skipping backup")
            return
        dst_files = _build_file_map(dst_dir) if os.path.isdir(dst_dir) else {}

        os.makedirs(dst_dir, exist_ok=True)
        logger.info(f"🤖 Backing up saves for {title}")

        # Copy/update files from source into backup
        for rel, src_path in src_files.items():
            dst_path = os.path.join(dst_dir, rel)
            _copy_file(src_path, dst_path)

        # Remove files from backup that no longer exist in source
        for rel, dst_path in dst_files.items():
            if rel not in src_files:
                try:
                    os.remove(dst_path)
                except OSError as e:
                    logger.error(f"❌ Error removing obsolete backup file {dst_path}: {e}")

        logger.info(f"✅ {title}: backup updated")
        return

    if strategy == "restore":
        if not os.path.isdir(dst_dir):
            logger.info(f"ℹ️ {title}: backup directory {dst_dir} not found, skipping restore")
            return
        os.makedirs(src_dir, exist_ok=True)
        logger.warning(f"⚠️ Restoring saves for {title} from backup (overwrites existing files)")
        _copy_tree_one_way(dst_dir, src_dir)
        logger.info(f"✅ {title}: restore completed")
        return

    # sync (metadata-aware) strategy
    src_exists = os.path.isdir(src_dir)
    dst_exists = os.path.isdir(dst_dir)

    if not src_exists and not dst_exists:
        logger.info(f"ℹ️ {title}: no save directory on either side, skipping")
        return

    src_files = _build_file_map(src_dir) if src_exists else {}
    dst_files = _build_file_map(dst_dir) if dst_exists else {}

    src_current = _max_mtime(src_files)
    dst_current = _max_mtime(dst_files)

    if src_current == 0.0 and dst_current == 0.0:
        logger.info(f"ℹ️ {title}: both save directories are empty, nothing to sync")
        return

    src_meta = _read_sync_meta(src_dir) if src_exists else None
    dst_meta = _read_sync_meta(dst_dir) if dst_exists else None

    use_meta = src_meta is not None and dst_meta is not None
    direction = None  # "src_to_dst" or "dst_to_src"

    if use_meta:
        src_changed = src_current > src_meta
        dst_changed = dst_current > dst_meta

        if src_changed and not dst_changed:
            direction = "src_to_dst"
        elif dst_changed and not src_changed:
            direction = "dst_to_src"
        elif not src_changed and not dst_changed:
            logger.info(f"ℹ️ {title}: no changes detected since last sync, skipping")
            return
        else:
            logger.warning(
                f"⚠️ {title}: changes detected on both original and backup since last sync; "
                "preferring original save directory as source"
            )
            direction = "src_to_dst"
    else:
        # First sync or missing metadata: compare latest modification times
        if dst_current > src_current:
            direction = "dst_to_src"
        else:
            direction = "src_to_dst"

    if direction == "src_to_dst":
        if not src_exists:
            logger.info(f"ℹ️ {title}: original save directory {src_dir} does not exist, skipping sync")
            return
        os.makedirs(dst_dir, exist_ok=True)
        source_root, target_root = src_dir, dst_dir
    else:
        if not dst_exists:
            logger.info(f"ℹ️ {title}: backup directory {dst_dir} does not exist, skipping sync")
            return
        os.makedirs(src_dir, exist_ok=True)
        source_root, target_root = dst_dir, src_dir

    source_files = _build_file_map(source_root)
    target_files = _build_file_map(target_root) if os.path.isdir(target_root) else {}

    direction_label = "original -> backup" if direction == "src_to_dst" else "backup -> original"
    logger.info(f"🤖 Syncing saves for {title}: {direction_label}")

    # Copy/update files from source into target
    for rel, src_path in source_files.items():
        dst_path = os.path.join(target_root, rel)
        _copy_file(src_path, dst_path)

    # Remove files from target that no longer exist in source
    for rel, dst_path in target_files.items():
        if rel not in source_files:
            try:
                os.remove(dst_path)
            except OSError as e:
                logger.error(f"❌ Error removing obsolete synced file {dst_path}: {e}")

    # Update metadata snapshots on both sides
    src_snapshot = _max_mtime(_build_file_map(src_dir) if os.path.isdir(src_dir) else {})
    dst_snapshot = _max_mtime(_build_file_map(dst_dir) if os.path.isdir(dst_dir) else {})
    _write_sync_meta(src_dir, src_snapshot)
    _write_sync_meta(dst_dir, dst_snapshot)

    logger.info(f"✅ {title}: saves synchronized (strategy=sync)")


def run(config: dict) -> None:
    games_dir = config.get("FREEGAMES_PATH")
    saves_root = config.get("SAVESCOPY_PATH")

    raw_strategy = (config.get("SAVESCOPY_STRATEGY") or "backup").strip().lower()
    if raw_strategy not in {"backup", "sync", "restore"}:
        logger.warning(
            f" Invalid SAVESCOPY_STRATEGY '{raw_strategy}', falling back to 'backup'"
        )
        strategy = "backup"
    else:
        strategy = raw_strategy

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
        logger.info("🤖 No launch_manifest.json found, nothing to process")
        return

    logger.info(f"🤖 Running saver with strategy='{strategy}' to {saves_root}")
    for manifest_path in manifests:
        _sync_one_manifest(manifest_path, saves_root, strategy)
