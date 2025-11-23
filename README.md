# Gamer Sidekick

A comprehensive tool for managing DRM-free games, emulator configurations, and game patches on Linux gaming systems like Steam Deck.

> **Note**: This project was developed using vibe coding techniques with extensive curation work. While primarily tested on Linux (Steam Deck), Windows compatibility is included but untested - it may work but hasn't been verified.

## Overview

Gamer Sidekick consists of four main modules:

1. **Configurer** - Automatically configures emulator settings based on your preferences
2. **Manifester** - Generates manifests for DRM-free games to import into Steam via Steam ROM Manager
3. **Patcher** - Applies patches and file replacements to games
4. **Saver** - Manages save backups and optional synchronization

## Installation & Usage

1. Clone or download this repository
2. Edit `config.txt` with your paths and preferences
3. Run the main script:
   ```bash
   # Linux/macOS
   ./gamer-sidekick.sh
   # or
   python3 gamer-sidekick.py
   
   # Windows
   gamer-sidekick.bat
   # or
   python gamer-sidekick.py
   ```

## Configuration File (config.txt)

The `config.txt` file contains all your settings and paths. Here's an example:

```ini
# Paths
FREEGAMES_PATH=/run/media/deck/SteamDeck-SD/linux-games
PATCHES_PATH=/run/media/deck/SteamDeck-SD/mods
SAVESCOPY_PATH=/run/media/deck/SteamDeck-SD/gamer-sidekick-backup
SAVESCOPY_STRATEGY=backup  # backup (default), sync, or restore (dangerous)

# Dolphin settings
DOLPHIN_GC_LANGUAGE=2   # 0=eng, 1=ger, 2=fre, 3=spa
DOLPHIN_WII_LANGUAGE=3  # 0=jap, 1=eng, 2=ger, 3=fre
DOLPHIN_GC_SKIP_BOOT=False

# RyuJinx settings
RYUJINX_LANGUAGE_CODE=fr_FR
RYUJINX_SYSTEM_LANGUAGE=French
RYUJINX_SYSTEM_REGION=Europe

# Cemu settings (1=eng, 2=fre)
CEMU_CONSOLE_LANGUAGE=2

# RetroArch settings (1=eng, 2=fre)
RETROARCH_USER_LANGUAGE=2
RETROARCH_VIDEO_DRIVER=glcore
RETROARCH_NETPLAY_NICKNAME=Jean
```

## Modules

### 1. Configurer

The configurer automatically modifies emulator configuration files based on your preferences in `config.txt`. It supports both text-based and binary file modifications.

#### Supported Emulators:
- **Dolphin** (GameCube/Wii) - Language settings, boot options, and binary SYSCONF modifications
- **Ryujinx** (Nintendo Switch) - Language, region, and system settings
- **Cemu** (Wii U) - Console language settings
- **RetroArch** - User interface language, video driver, netplay nickname

#### Configuration Examples:

**Text Replacements** (JSON configuration files, INI files):
```json
{
    "name": "language code",
    "pattern": "\"language_code\":.*,",
    "value": "\"language_code\": \"${RYUJINX_LANGUAGE_CODE}\","
}
```

**Hexadecimal Replacements** (Binary files like Dolphin's SYSCONF):
```json
{
    "name": "Wii language",
    "type": "hexadecimal",
    "pattern": "IPL.LNG?",
    "value": "IPL.LNG${DOLPHIN_WII_LANGUAGE}"
}
```

The configurer supports environment variable substitution using `${VARIABLE_NAME}` syntax and can handle multiple installation paths (native and Flatpak versions).

#### Variable Validation:
The configurer automatically validates all variables before applying configurations. If any required variables are undefined in `config.txt`, the system will:
- Skip the specific configuration with a clear warning
- Show exactly which variables are missing
- Group warnings by emulator for easy identification

Example output when variables are missing:
```
🔧 Configuring Dolphin...
⚠️  Skipping GameCube language - undefined variables: DOLPHIN_GC_LANGUAGE
⚠️  Skipping Wii language - undefined variables: DOLPHIN_WII_LANGUAGE
```

### 2. Manifester

The manifester generates manifest files for DRM-free games so they can be easily imported into Steam using [Steam ROM Manager](https://github.com/SteamGridDB/steam-rom-manager).

#### How it works:
1. Scans your `FREEGAMES_PATH` directory for game folders
2. Automatically detects executable files in each game directory
3. Generates individual `launch_manifest.json` files for each game
4. Creates a master `manifests.json` file containing all games

#### Generated Files:

**Individual Game Manifest** (`launch_manifest.json`):
```json
{
    "title": "Game Name",
    "target": "./game_executable",
    "startIn": "./",
    "launchOptions": ""
}
```

**Master Manifest** (`manifests.json`):
```json
[
    {
        "title": "Game 1",
        "target": "/full/path/to/game1/executable",
        "startIn": "/full/path/to/game1/",
        "launchOptions": ""
    },
    {
        "title": "Game 2",
        "target": "/full/path/to/game2/executable",
        "startIn": "/full/path/to/game2/",
        "launchOptions": ""
    }
]
```

#### Important Notes:
- The manifester automatically detects the best executable file by matching folder names
- If the generated information is incorrect, you can manually edit the `launch_manifest.json` files
- The master `manifests.json` file is used by Steam ROM Manager for bulk import

### 3. Patcher

The patcher applies file patches and replacements to games using a `patch.json` configuration file.

#### Supported Operations:
- **File Replacement** - Replace entire files
- **Binary Patching** - Apply BPS patches with CRC32 verification

#### Patch Configuration (`patch.json`):

```json
[
    {
        "file": "mus_ohyes.ogg",
        "target": "Undertale/mus_ohyes.ogg",
        "method": "replace"
    },
    {
        "file": "patch_steam.bps",
        "target": "Undertale/data.win",
        "target_crc32": "D3D27C56",
        "patched_crc32": "1655BF6C",
        "method": "patch"
    }
]
```

#### Patch Types:

**File Replacement:**
- `file`: Source file in your patches directory
- `target`: Target file to replace (relative to game directory)
- `method`: "replace"

**Binary Patching:**
- `file`: BPS patch file in your patches directory
- `target`: Target file to patch
- `target_crc32`: Expected CRC32 of the original file (for verification)
- `patched_crc32`: Expected CRC32 of the patched file (for verification)
- `method`: "patch"

#### Features:
- CRC32 verification ensures patches are applied to correct files
- Automatic backup creation before patching
- Skip already patched files (detected by CRC32)
- Comprehensive error handling and logging

### 4. Saver

The saver manages per-game save data using `SAVESCOPY_PATH` and `SAVESCOPY_STRATEGY`.

Each game manifest can declare a `savePath`. For every manifest with a valid `savePath`, the saver:
- Resolves the original save directory (`savePath`)
- Creates a sanitized subfolder under `SAVESCOPY_PATH` based on the game title
- Applies the selected strategy between the original and backup folders

#### Configuration

- `SAVESCOPY_PATH` – Root directory where per-game save backups are stored.
- `SAVESCOPY_STRATEGY` – One of:
  - `backup` (default, recommended)
  - `sync`
  - `restore` (dangerous)

If `SAVESCOPY_STRATEGY` is missing or invalid, the tool automatically falls back to `backup`.

#### Strategies

- **backup (default, recommended)**
  - One-way copy from the original save directory (`savePath`) to the backup directory under `SAVESCOPY_PATH`.
  - Existing files in the backup are overwritten by the originals when they share the same relative path.
  - The original save directory is never modified by this mode.

- **sync**
  - Metadata-aware one-way mirroring between the original and backup directories.
  - A hidden `.gamer-sidekick` metadata file is stored in each directory to track the last sync snapshot.
  - On first sync (no metadata), the side with the most recently modified files is mirrored to the other side.
  - On later syncs, only the side that changed since the last snapshot is mirrored to the other; if both changed, the original save directory is preferred and a warning is logged.

- **restore (dangerous)**
  - One-way copy from the backup directory under `SAVESCOPY_PATH` back to the original save directory.
  - Existing files in the original directory are overwritten by the backup when they share the same relative path.
  - Intended for recovery after reinstalling or moving games; use with caution.

#### Safety guidelines

- Start with the `backup` strategy until you have confirmed your manifests and paths.
- Use `sync` only if you understand that newer files from either side can overwrite older ones.
- Use `restore` only when you explicitly want to replace current saves with the backup contents.
- For critical games, keep an additional external backup before changing strategies.

## Directory Structure

```
gamer-sidekick/
├── gamer-sidekick.py          # Main script
├── gamer-sidekick.sh          # Shell wrapper (Linux/macOS)
├── gamer-sidekick.bat         # Batch script (Windows)
├── gamer-sidekick.ps1         # PowerShell script (Windows)
├── config.txt                 # Configuration file
├── README.md                  # This file
├── lib/
│   ├── configurer.py          # Emulator configuration module
│   ├── configurer.json        # Emulator configuration definitions
│   ├── manifester.py          # Game manifest generation module
│   └── patcher.py             # Game patching module
└── scripts/
    ├── install_bios.sh        # BIOS installation script
    └── move_rom_zips.sh       # ROM organization script
```

## Requirements

- Python 3.6+ (no external Python packages required - uses only standard library)
- Standard Linux utilities (find, file, etc.)
- For patching: **flips** command-line tool for BPS patch support
  - Download from: https://github.com/Alcaro/Flips/releases
  - Place the `flips` binary in `bin/flips` relative to the project root
  - Or ensure `flips` is available in your system PATH

## Platform Support

- **Linux**: Fully tested and supported (Steam Deck, desktop Linux)
- **Windows**: Configuration paths included but untested - may work with proper Python environment

## Steam ROM Manager Integration

1. Install [Steam ROM Manager](https://github.com/SteamGridDB/steam-rom-manager)
2. Run gamer-sidekick to generate manifests
3. In Steam ROM Manager, configure a parser to use the generated `manifests.json`
4. Parse and add games to Steam

The manifester makes it easy to manage large collections of DRM-free games by automatically detecting executables and generating the necessary metadata for Steam integration.
