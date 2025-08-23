import json
import os
import shutil
import subprocess
import glob
import zlib
import logging
import re
from pathlib import Path

logger = logging.getLogger("patcher")

FLIPS_PATH = Path(__file__).resolve().parent.parent / 'bin' / 'flips'

def load_games_locations():
    """Load game directory locations from JSON file"""
    json_path = Path(__file__).resolve().parent / 'games_locations.json'
    with open(json_path, 'r') as f:
        locations = json.load(f)
    
    # Combine all directories and resolve environment variables
    all_dirs = locations.get('steam_directories', []) + locations.get('other_game_directories', [])
    resolved_dirs = []
    
    for path in all_dirs:
        # Resolve environment variables
        resolved_path = os.path.expandvars(path)
        
        # Handle wildcards by expanding them
        if '*' in resolved_path:
            expanded_paths = glob.glob(resolved_path)
            resolved_dirs.extend(expanded_paths)
        else:
            resolved_dirs.append(resolved_path)
    
    return resolved_dirs

def check_flips_availability():
    """Check if flips command is available"""
    # First try local bin/flips
    if FLIPS_PATH.exists() and os.access(FLIPS_PATH, os.X_OK):
        return str(FLIPS_PATH)
    
    # Then try system PATH
    try:
        result = subprocess.run(['which', 'flips'], capture_output=True, text=True)
        if result.returncode == 0:
            return 'flips'
    except FileNotFoundError:
        pass
    
    return None


def calculate_crc32(filename):
    with open(filename, 'rb') as file:
        return zlib.crc32(file.read()) & 0xFFFFFFFF

def get_game_dirs():
    game_locations = load_games_locations()
    return [p for p in game_locations if os.path.exists(p)]

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
                logger.info(f"✅ {target_file} already replaced")
                return
            else:
                logger.error(f"❌ {target_file} backup exists but target file differ from patch")
                return
    else:
        shutil.copy2(target_file, backup_file)
    
    shutil.copy2(source_file, target_file)
    logger.info(f"✅ {target_file} replaced")

def patch_file_with_backup_check(patch_info, source_file, target_file, flips_cmd):
    backup_file = f"{target_file}.backup"
    
    # Check CRC32 before attempting to patch
    target_crc32_expected = patch_info.get('target_crc32')
    if target_crc32_expected:
        actual_crc32 = calculate_crc32(target_file)
        expected_crc32 = int(target_crc32_expected, 16)
        if actual_crc32 != expected_crc32:
            logger.error(f"❌ CRC32 mismatch for {target_file}. Expected: {target_crc32_expected}, Got: {actual_crc32:08X}")
            return
    
    if os.path.exists(backup_file):
        target_crc32 = calculate_crc32(target_file)
        backup_crc32 = calculate_crc32(backup_file)
        
        if target_crc32 != backup_crc32:
            patched_crc32 = patch_info.get('patched_crc32')
            if patched_crc32 and target_crc32 == int(patched_crc32, 16):
                logger.info(f"✅ {target_file} already patched")
                return
            else:
                logger.error(f"❌ {target_file} backup exists but target file differ from patch")
                return
    else:
        shutil.copy2(target_file, backup_file)
    
    cmd = f"'{flips_cmd}' -a '{source_file}' '{target_file}' '{target_file}.patched'"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        os.replace(f"{target_file}.patched", target_file)
        logger.info(f"✅ {target_file} patched")
    else:
        logger.error(f"❌ Error patching {target_file}: {result.stderr}")

def apply_patch_to_file(patch_info, source_file, target_file, flips_cmd):
    if patch_info['method'] == 'replace':
        apply_replacement(source_file, target_file)
    elif patch_info['method'] == 'patch':
        patch_file_with_backup_check(patch_info, source_file, target_file, flips_cmd)


def process_single_patch(patch_info, patch_folder, flips_cmd):
    source_file = os.path.join(patch_folder, patch_info['file'])
    if not os.path.exists(source_file):
        logger.error(f"❌ {source_file} does not exist")
        return
    
    for games_folder in get_game_dirs():
        target_file = os.path.join(games_folder, patch_info['target'])
        if not os.path.exists(target_file):
            continue
            
        status = check_file_status(target_file, patch_info.get('target_crc32'), patch_info.get('patched_crc32'))
        
        if status == "already_patched":
            logger.info(f"✅ {target_file} already patched")
        elif status == "ready":
            apply_patch_to_file(patch_info, source_file, target_file, flips_cmd)
        
        return
    
    logger.info(f"❌ {patch_info['target']} not found")

def run(config: dict):
    patches_dir = config.get('PATCHES_PATH')
    if not patches_dir or not os.path.isdir(patches_dir):
        logger.warning("🤖 PATCHES_PATH not configured or invalid")
        return

    # Check flips availability once at startup
    flips_cmd = check_flips_availability()
    if not flips_cmd:
        logger.warning("🤖 flips command not found - skipping patcher phase")
        logger.info("ℹ️  Install flips from https://github.com/Alcaro/Flips/releases")
        logger.info("ℹ️  Place in bin/flips or ensure it's in your system PATH")
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
            process_single_patch(patch, patch_folder, flips_cmd)
        
        patch_count += 1
    
    if patch_count == 0:
        logger.info("ℹ️  No patch.json files found")
