import json
import os
import shutil
import subprocess
import glob
import zlib
import logging
from pathlib import Path
 
logger = logging.getLogger("patcher")

GAMES_FOLDERS = [
    "/home/deck/.steam/steam/steamapps/common",
    "/run/media/deck/*/steamapps/common",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
FLIPS_PATH = REPO_ROOT / 'bin' / 'flips'

def calculate_crc32(filename):
    with open(filename, 'rb') as file:
        return zlib.crc32(file.read()) & 0xFFFFFFFF

def flatten_game_folders(folders):
    paths = (glob.glob(f) if '*' in f else [f] for f in folders)
    flat = (p for group in paths for p in group)
    return list({p for p in flat if os.path.exists(p)})

def get_file_paths(patch_info, games_folder, patch_folder):
    source_file = os.path.join(patch_folder, patch_info['file'])
    target_file = os.path.join(games_folder, patch_info['target'])
    backup_file = f"{target_file}.backup"
    return source_file, target_file, backup_file

def create_backup(target_file, backup_file):
    if not os.path.exists(backup_file):
        shutil.copy2(target_file, backup_file)
        return True
    return False

def replace_file(source_file, target_file):
    shutil.copy2(source_file, target_file)
    logger.info(f"✅ {os.path.basename(target_file)} replaced")

def apply_bps_patch(patch_file, target_file):
    command = f"'{str(FLIPS_PATH)}' -a '{patch_file}' '{target_file}' '{target_file}.patched'"
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        os.replace(f"{target_file}.patched", target_file)
        logger.info(f"✅ {os.path.basename(target_file)} patched")
        return True
    logger.error(f"❌ Error patching {os.path.basename(target_file)}: {result.stderr}")
    return False

def check_crc32(file_path, expected_crc32):
    if expected_crc32 is None:
        return True
    actual_crc32 = calculate_crc32(file_path)
    logger.info(f"- CRC before patching: {actual_crc32:08X}")
    if actual_crc32 != int(expected_crc32, 16):
        logger.warning(f"❌ CRC mismatch. Expected: {expected_crc32}, Got: {actual_crc32:08X}")
        return False
    return True

def patch_file(patch_info, source_file, target_file, backup_file):
    if not create_backup(target_file, backup_file):
        logger.info(f"- {os.path.basename(target_file)} backup exists, skipping patch")
        return

    if patch_info['method'] == 'replace':
        replace_file(source_file, target_file)
    elif patch_info['method'] == 'patch':
        if not apply_bps_patch(source_file, target_file):
            os.remove(backup_file)
            return

    logger.info(f"- CRC after patching: {calculate_crc32(target_file):08X}")

def apply_patch(patch_info, games_folder, patch_folder):
    source_file, target_file, backup_file = get_file_paths(patch_info, games_folder, patch_folder)

    if not os.path.exists(source_file):
        logger.error(f"❌ {os.path.basename(source_file)} does not exist")
        return

    if not os.path.exists(target_file):
        return

    logger.info(f"✅ {os.path.basename(target_file)} found")

    if not check_crc32(target_file, patch_info.get('target_crc32')):
        return

    patch_file(patch_info, source_file, target_file, backup_file)

def process_patch_file(json_file):
    patch_folder = os.path.dirname(json_file)
    with open(json_file, 'r') as f:
        patches = json.load(f)

    game_dirs = flatten_game_folders(GAMES_FOLDERS)
    for patch in patches:
        for games_folder in game_dirs:
            apply_patch(patch, games_folder, patch_folder)


def run(config: dict):
    patches_dir = config.get('PATCHES_PATH')
    if not os.path.isdir(patches_dir):
        logger.warning(f"❌ {patches_dir} is not a valid directory")
        return

    for patch_folder in os.listdir(patches_dir):
        json_file = os.path.join(patches_dir, patch_folder, 'patch.json')
        if os.path.exists(json_file):
            process_patch_file(json_file)
