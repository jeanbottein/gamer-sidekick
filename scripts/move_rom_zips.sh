#!/usr/bin/env bash
# move_rom_zips.sh
# Recursively move .zip files from Emulation/roms to retrodeck/roms, preserving subdirectory structure.
# Conditions:
# - Only move if the destination subdirectory exists.
# - Only move if the destination file does not already exist.
# - Log only problems to stderr.

SRC_ROOT="/run/media/deck/SteamDeck-SD/Emulation/roms"
DEST_ROOT="/run/media/deck/SteamDeck-SD/retrodeck/roms"

# Verify roots exist; if not, it's a problem.
if [[ ! -d "$SRC_ROOT" ]]; then
  echo "Source root does not exist: $SRC_ROOT" >&2
  exit 1
fi
if [[ ! -d "$DEST_ROOT" ]]; then
  echo "Destination root does not exist: $DEST_ROOT" >&2
  exit 1
fi

# Find zip files and process them safely with null-delimited paths.
 # Find ROM archive files by extension (case-insensitive):
 # zip, rvz, chd, sbi, wua, wad, nsp, 3ds, 7z, zar, xci, wux, iso
 find "$SRC_ROOT" -type f \
   -iregex ".*\\.\(zip\|rvz\|chd\|sbi\|wua\|wad\|nsp\|3ds\|7z\|zar\|xci\|wux\|iso\)$" \
   -print0 | while IFS= read -r -d '' src; do
  # Compute relative path from SRC_ROOT
  rel="${src#"$SRC_ROOT"/}"
  subdir="$(dirname "$rel")"
  dest_dir="$DEST_ROOT/$subdir"
  base="$(basename "$src")"
  dest="$dest_dir/$base"

  # Only move if destination subdir exists and target file doesn't exist
  if [[ -d "$dest_dir" && ! -e "$dest" ]]; then
    if ! mv -n -- "$src" "$dest"; then
      echo "Failed to move: $src -> $dest" >&2
    fi
  fi
  # No logs for skipped moves by design (log only problems).

done
