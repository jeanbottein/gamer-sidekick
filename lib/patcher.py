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

FLIPS_PATH = Path(__file__).resolve().parent.parent / 'bin' / 'flips'

def calculate_crc32(filename):
    with open(filename, 'rb') as file:
        return zlib.crc32(file.read()) & 0xFFFFFFFF

def get_game_dirs():
    paths = (glob.glob(f) if '*' in f else [f] for f in GAMES_FOLDERS)
    return [p for group in paths for p in group if os.path.exists(p)]

def check_file_status(file_path, target_crc32, patched_crc32):
    actual_crc32 = calculate_crc32(file_path)
    
    if patched_crc32 and actual_crc32 == int(patched_crc32, 16):
        return "already_patched"
    
    if not target_crc32 or actual_crc32 == int(target_crc32, 16):
        return "ready"
    
    logger.warning(f"❌ CRC mismatch. Expected: {target_crc32}, Got: {actual_crc32:08X}")
    return "mismatch"

def apply_replacement(source_file, target_file):
    backup_file = f"{target_file}.backup"
    
    if os.path.exists(backup_file):
        target_crc32 = calculate_crc32(target_file)
        backup_crc32 = calculate_crc32(backup_file)
        
        if target_crc32 != backup_crc32:
            source_crc32 = calculate_crc32(source_file)
            if target_crc32 == source_crc32:
                logger.info(f"✅ {os.path.basename(target_file)} already replaced")
                return
            else:
                logger.error(f"❌ {os.path.basename(target_file)} backup exists but target file differ from patch")
                return
    else:
        shutil.copy2(target_file, backup_file)
    
    shutil.copy2(source_file, target_file)
    logger.info(f"✅ {os.path.basename(target_file)} replaced")

def patch_file_with_backup_check(patch_info, source_file, target_file):
    backup_file = f"{target_file}.backup"
    
    if os.path.exists(backup_file):
        target_crc32 = calculate_crc32(target_file)
        backup_crc32 = calculate_crc32(backup_file)
        
        if target_crc32 != backup_crc32:
            patched_crc32 = patch_info.get('patched_crc32')
            if patched_crc32 and target_crc32 == int(patched_crc32, 16):
                logger.info(f"✅ {os.path.basename(target_file)} already patched")
                return
            else:
                logger.error(f"❌ {os.path.basename(target_file)} backup exists but target file differ from patch")
                return
    else:
        shutil.copy2(target_file, backup_file)
    
    cmd = f"'{FLIPS_PATH}' -a '{source_file}' '{target_file}' '{target_file}.patched'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        os.replace(f"{target_file}.patched", target_file)
        logger.info(f"✅ {os.path.basename(target_file)} patched")
    else:
        logger.error(f"❌ Error patching {os.path.basename(target_file)}: {result.stderr}")

def apply_patch_to_file(patch_info, source_file, target_file):
    if patch_info['method'] == 'replace':
        apply_replacement(source_file, target_file)
    elif patch_info['method'] == 'patch':
        apply_patch(source_file, target_file)


def process_single_patch(patch_info, patch_folder):
    source_file = os.path.join(patch_folder, patch_info['file'])
    
    if not os.path.exists(source_file):
        logger.error(f"❌ {os.path.basename(source_file)} does not exist")
        return
    
    for games_folder in get_game_dirs():
        target_file = os.path.join(games_folder, patch_info['target'])
        if not os.path.exists(target_file):
            continue
            
        status = check_file_status(target_file, patch_info.get('target_crc32'), patch_info.get('patched_crc32'))
        
        if status == "already_patched":
            logger.info(f"✅ {os.path.basename(target_file)} already patched")
        elif status == "ready":
            apply_patch_to_file(patch_info, source_file, target_file)
        
        return
    
    logger.info(f"❌ {patch_info['target']} not found")

def run(config: dict):
    patches_dir = config.get('PATCHES_PATH')
    if not patches_dir or not os.path.isdir(patches_dir):
        logger.warning("❌ PATCHES_PATH not configured or invalid")
        return

    logger.info(f"🤖 Looking for patches in {patches_dir}")
    patch_count = 0
    
    for root, dirs, files in os.walk(patches_dir):
        if 'patch.json' not in files:
            continue
            
        json_file = os.path.join(root, 'patch.json')
        relative_path = os.path.relpath(root, patches_dir)
        logger.info(f"📦 Processing {relative_path}")
        
        with open(json_file, 'r') as f:
            patches = json.load(f)
        
        patch_folder = os.path.dirname(json_file)
        for patch in patches:
            process_single_patch(patch, patch_folder)
        
        patch_count += 1
    
    if patch_count == 0:
        logger.info("ℹ️  No patch.json files found")
