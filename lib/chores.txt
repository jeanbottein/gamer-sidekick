#!/usr/bin/env python3

import os
from pathlib import Path
import subprocess
import re

MYCONFIG = "/run/media/deck/SteamDeck-SD/scripts"
HOME = "/home/deck"
# Keep EMUPATH for texturepack paths used below
EMUPATH = "/run/media/deck/SteamDeck-SD/Emulation"
# Resolve repo root and rclone from bin/
REPO_ROOT = Path(__file__).resolve().parent.parent
RCLONE_BIN = REPO_ROOT / 'bin' / 'rclone'
RCLONE = f"{RCLONE_BIN} --config {HOME}/.config/rclone/rclone.conf"

def modify_file(file_path, replacements):
    if not os.path.exists(file_path):
        return
    with open(file_path, 'r') as file:
        content = file.read()
    for old, new in replacements:
        content = re.sub(old, new, content)
    with open(file_path, 'w') as file:
        file.write(content)

def configure_emulators():
    print("Configuring emulators")
    config_changes = {
        f"{HOME}/.config/Ryujinx/Config.json": [
            ("en_US", "fr_FR"),
            (r'"language_code":.*,', '"language_code": "fr_FR",'),
            (r'"system_language":.*,', '"system_language": "French",'),
            (r'"system_region":.*,', '"system_region": "Europe",')
        ],
        f"{HOME}/.config/Cemu/settings.xml": [
            (r'<console_language>.*</console_language>', '<console_language>2</console_language>')
        ],
        f"{HOME}/.var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg": [
            (r'user_language =.*', 'user_language = "2"'),
            (r'video_driver =.*', 'video_driver = "glcore"'),
            (r'netplay_nickname =.*', 'netplay_nickname = "Jean"')
        ]
    }
    for file_path, replacements in config_changes.items():
        modify_file(file_path, replacements)

def create_symlink(src_dir, tgt_dir):
    if not os.path.isdir(src_dir):
        print(f"Error: Source directory {src_dir} does not exist")
        return

    if os.path.islink(tgt_dir) and os.path.realpath(tgt_dir) == os.path.realpath(src_dir):
        print(f"Target directory {tgt_dir} is already correctly linked to {src_dir}")
        return

    if os.path.exists(tgt_dir):
        if os.path.islink(tgt_dir):
            print(f"Error: Target directory {tgt_dir} is already a symbolic link to a different location")
        elif os.path.isdir(tgt_dir) and os.listdir(tgt_dir):
            print(f"Error: Target directory {tgt_dir} is not empty")
        else:
            os.rmdir(tgt_dir)
            os.symlink(src_dir, tgt_dir)
            print(f"Symbolic link created from {tgt_dir} to {src_dir}")
    else:
        os.symlink(src_dir, tgt_dir)
        print(f"Symbolic link created from {tgt_dir} to {src_dir}")

def run_rclone_command(cmd):
    return subprocess.call(cmd, shell=True) == 0

def sync_directories(src_dir, tgt_dir):
    base_cmd = f"{RCLONE} bisync {src_dir} {tgt_dir} --copy-links"
    if run_rclone_command(f"{base_cmd} --resync-mode path1"):
        return
    print("Bisync failed, attempting resync...")
    if run_rclone_command(f"{base_cmd} --resync --resync-mode path1"):
        return
    print("Resync also failed, performing copy...")
    run_rclone_command(f"{RCLONE} copy {src_dir} {tgt_dir} --copy-links")

def create_directories():
    dirs_to_create = [
        "mods",
        f"{HOME}/.local/share/citra-emu/load/textures",
        f"{HOME}/.local/share/citra-emu/load/mods",
        f"{HOME}/.local/share/lime3ds-emu/load/textures",
        f"{HOME}/.local/share/lime3ds-emu/load/mods",
        f"{EMUPATH}/texturepacks/dolphin",
        f"{EMUPATH}/texturepacks/citra",
        f"{EMUPATH}/texturepacks/lime3ds"
    ]
    for dir_path in dirs_to_create:
        os.makedirs(dir_path, exist_ok=True)

def run_python_scripts():
    subprocess.call(f"python {MYCONFIG}/manifester.py '/run/media/deck/SteamDeck-SD/linux-games'", shell=True)
    subprocess.call(f"python {MYCONFIG}/patcher.py", shell=True)

def create_symlinks():
    symlinks = [
        (f"{HOME}/.local/share/lime3ds-emu/load/textures", f"{HOME}/.local/share/citra-emu/load/textures"),
        (f"{HOME}/.local/share/lime3ds-emu/load/mods", f"{HOME}/.local/share/citra-emu/load/mods"),
        (f"{HOME}/.local/share/lime3ds-emu/load/textures", f"{EMUPATH}/texturepacks/lime3ds/textures"),
        (f"{HOME}/.local/share/lime3ds-emu/load/mods", f"{EMUPATH}/texturepacks/lime3ds/mods"),
        (f"{HOME}/.local/share/citra-emu/load/textures", f"{EMUPATH}/texturepacks/citra/textures"),
        (f"{HOME}/.local/share/citra-emu/load/mods", f"{EMUPATH}/texturepacks/citra/mods"),
        (f"{HOME}/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Load/Textures", f"{EMUPATH}/texturepacks/dolphin/Textures"),
        (f"{HOME}/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/Load/GraphicMods", f"{EMUPATH}/texturepacks/dolphin/GraphicMods"),
        (f"{HOME}/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/ResourcePacks", f"{EMUPATH}/texturepacks/dolphin/ResourcePacks")
    ]
    for src, tgt in symlinks:
        create_symlink(src, tgt)

def sync_all_directories():
    sync_directories(f"{EMUPATH}/texturepacks", "onedrive:EmuDeck/texturepacks")
    sync_directories(MYCONFIG, "onedrive:Devices/SteamDeck/Scripts")
    sync_directories(f"{HOME}/.config/steam-rom-manager/userData", "onedrive:Devices/SteamDeck/Config/steam-rom-manager-user-data")

def main():
    create_directories()
    configure_emulators()
    run_python_scripts()
    create_symlinks()
    sync_all_directories()
    print("Done")

if __name__ == "__main__":
    main()
