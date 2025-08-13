import json
import os
import shutil
import subprocess
import glob
import zlib
from pathlib import Path

GAMES_FOLDERS = ["/home/deck/.steam/steam/steamapps/common", "/run/media/deck/*/steamapps/common"]
PATCHES_FOLDER = 'patches'

def calculate_crc32(filename):
    with open(filename, 'rb') as file:
        return zlib.crc32(file.read()) & 0xFFFFFFFF

def flatten_game_folders(folders):
    return list(set(filter(os.path.exists, [path for folder in folders for path in ([folder] if '*' not in folder else glob.glob(folder))])))

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
    print(f"Replaced {target_file} with {source_file}")

def apply_bps_patch(patch_file, target_file):
    # Resolve flips binary from repo root: <repo>/bin/flips
    repo_root = Path(__file__).resolve().parent.parent
    flips_path = repo_root / 'bin' / 'flips'
    command = f"'{str(flips_path)}' -a '{patch_file}' '{target_file}' '{target_file}.patched'"
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        os.replace(f"{target_file}.patched", target_file)
        print(f"Successfully patched {target_file}")
        return True
    print(f"Error patching {target_file}: {result.stderr}")
    return False

def check_crc32(file_path, expected_crc32):
    if expected_crc32 is None:
        return True
    actual_crc32 = calculate_crc32(file_path)
    print(f"CRC before patching: {actual_crc32:08X}")
    if actual_crc32 != int(expected_crc32, 16):
        print(f"CRC mismatch. Expected: {expected_crc32}, Got: {actual_crc32:08X}")
        return False
    return True

def patch_file(patch_info, source_file, target_file, backup_file):
    if not create_backup(target_file, backup_file):
        print(f"Backup file exists for {target_file}. Skipping patch.")
        return

    if patch_info['method'] == 'replace':
        replace_file(source_file, target_file)
    elif patch_info['method'] == 'patch':
        if not apply_bps_patch(source_file, target_file):
            os.remove(backup_file)
            return

    print(f"CRC after patching: {calculate_crc32(target_file):08X}")

def apply_patch(patch_info, games_folder, patch_folder):
    source_file, target_file, backup_file = get_file_paths(patch_info, games_folder, patch_folder)

    if not os.path.exists(source_file):
        print(f"Error: {source_file} does not exist")
        return

    if not os.path.exists(target_file):
        return

    print(f"Found {target_file}")

    if not check_crc32(target_file, patch_info.get('target_crc32')):
        return

    patch_file(patch_info, source_file, target_file, backup_file)

def process_patch_file(json_file):
    patch_folder = os.path.dirname(json_file)
    with open(json_file, 'r') as f:
        patches = json.load(f)

    for patch in patches:
        for games_folder in flatten_game_folders(GAMES_FOLDERS):
            apply_patch(patch, games_folder.strip(), patch_folder)


def run(config: dict):
    PATCHES_FOLDER = config.get('PATCHES_PATH')
    if not os.path.isdir(PATCHES_FOLDER):
        print(f"{PATCHES_FOLDER} is not a valid directory.")
        return

    for patch_folder in os.listdir(PATCHES_FOLDER):
        json_file = os.path.join(PATCHES_FOLDER, patch_folder, 'patch.json')
        if os.path.exists(json_file):
            process_patch_file(json_file)
