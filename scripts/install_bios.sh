#!/usr/bin/env bash
set -euo pipefail

# Usage: ./install_bios.sh [system]
# Optional system parameter to filter BIOS files by system (e.g., ps2, dreamcast, etc.)
SYSTEM_FILTER="${1:-}"

# ========== User-configurable variables ==========
# Where to look for BIOS files to copy from (searched recursively)
# Allow override via environment: export BIOS_SOURCE_PATH=... before running
BIOS_SOURCE_PATH="${BIOS_SOURCE_PATH:-/home/deck/Downloads/351ELEC-20211122-BIOS}"

# Default destination directory when JSON does not specify a path
# Allow override via environment
BIOS_TARGET_PATH="${BIOS_TARGET_PATH:-/run/media/deck/SteamDeck-SD/retrodeck/bios}"

# Variables that may appear inside JSON paths (customize for your setup)
roms_folder="${BIOS_TARGET_PATH}/../roms"
bios_folder="${BIOS_TARGET_PATH}"
saves_folder="${BIOS_TARGET_PATH}/../saves"

# URL of the BIOS definition JSON
BIOS_JSON_URL="https://raw.githubusercontent.com/RetroDECK/RetroDECK/cooker/config/retrodeck/reference_lists/bios.json"

# ========== End of user-configurable variables ==========

# Colors and symbols
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
BOLD="\033[1m"
RESET="\033[0m"
CHECK="✔"
CROSS="✘"
INFO="➜"

# Requirements check
need() { command -v "$1" >/dev/null 2>&1 || { echo -e "${RED}${CROSS}${RESET} Missing dependency: $1"; exit 1; }; }
need curl
need jq
need md5sum

# Validate paths exist
if [[ ! -d "$BIOS_SOURCE_PATH" ]]; then
  echo -e "${RED}${CROSS}${RESET} BIOS_SOURCE_PATH does not exist: $BIOS_SOURCE_PATH"
  exit 1
fi
if [[ ! -d "$BIOS_TARGET_PATH" ]]; then
  echo -e "${YELLOW}${INFO}${RESET} Creating BIOS_TARGET_PATH: $BIOS_TARGET_PATH"
  mkdir -p "$BIOS_TARGET_PATH"
fi

# Fetch JSON to temp
TMP_JSON="$(mktemp)"
trap 'rm -f "$TMP_JSON"' EXIT

echo -e "${BLUE}${INFO}${RESET} Downloading BIOS list JSON..."
if ! curl -fsSL "$BIOS_JSON_URL" -o "$TMP_JSON"; then
  echo -e "${RED}${CROSS}${RESET} Failed to download BIOS JSON from: $BIOS_JSON_URL"
  exit 1
fi

# Helper: expand variables like $roms_folder in a string using current shell variables
expand_vars() {
  local s="$1"
  # Use parameter expansion via eval on a quoted string; restrict to our known vars
  # shellcheck disable=SC2086,SC2163
  local out
  out=$(eval echo "$s")
  printf '%s' "$out"
}

# Debug helper (enable with DEBUG=1 environment variable)
DEBUG="${DEBUG:-0}"
debug() {
  if [[ "$DEBUG" == "1" ]]; then
    echo -e "${YELLOW}${INFO}${RESET} [DEBUG] $*"
  fi
}

# Helper to check if a string looks like an MD5 hash (32 hex chars)
is_md5() {
  [[ "$1" =~ ^[0-9a-fA-F]{32}$ ]]
}

# Build indexes of source files for fast lookup
declare -A SOURCE_INDEX  # lowercased filename -> full path
declare -A MD5_INDEX     # md5 hash -> full path

build_source_index() {
  echo -e "${BLUE}${INFO}${RESET} Building file and MD5 indexes..."
  
  # Using -printf to avoid subshell stat calls; store first-seen path for a given filename
  while IFS=$'\t' read -r base path; do
    # lowercase key for case-insensitive matching
    local key="${base,,}"
    if [[ -z "${SOURCE_INDEX[$key]:-}" ]]; then
      SOURCE_INDEX[$key]="$path"
    fi
  done < <(find "$BIOS_SOURCE_PATH" -type f -printf '%f\t%p\n' 2>/dev/null || true)
  
  # Build MD5 index for all source files
  while IFS= read -r -d '' filepath; do
    if [[ -f "$filepath" ]]; then
      local md5hash
      md5hash=$(md5sum "$filepath" 2>/dev/null | cut -d' ' -f1)
      if [[ -n "$md5hash" && -z "${MD5_INDEX[$md5hash]:-}" ]]; then
        MD5_INDEX[$md5hash]="$filepath"
      fi
    fi
  done < <(find "$BIOS_SOURCE_PATH" -type f -print0 2>/dev/null || true)
}

# Parse JSON with jq. We ignore the "required" field as requested.
# Output: filename \t first_path_or_empty \t md5_hash (for each MD5 if multiple)
parse_json() {
  local system_filter="$1"
  local jq_filter=''
  
  if [[ -n "$system_filter" ]]; then
    jq_filter="| select(.value.system == \"$system_filter\")"
  fi
  
  jq -r "
    .bios
    | to_entries[]
    $jq_filter
    | . as \$entry
    | (
        if (\$entry.value.md5 | type) == \"array\" then
          \$entry.value.md5[]
        else
          (\$entry.value.md5 // \"\")
        end
      ) as \$md5
    | (
        if (\$entry.value.paths | type) == \"array\" then
          \$entry.value.paths[0]
        elif (\$entry.value.paths | type) == \"string\" then
          \$entry.value.paths
        else
          \"\"
        end
      ) as \$path
    | \"\(\$entry.key)\u001f\(\$path)\u001f\(\$md5)\"
  " "$TMP_JSON"
}

# Report header
echo -e "${BOLD}BIOS sync start${RESET}"
if [[ -n "$SYSTEM_FILTER" ]]; then
  echo -e "  System Filter: ${BOLD}$SYSTEM_FILTER${RESET}"
fi
echo -e "  From: $BIOS_SOURCE_PATH\n  Default To: $BIOS_TARGET_PATH\n  JSON: $BIOS_JSON_URL\n"

# Counters
ok_count=0
fail_count=0
processed=0

# Buffer JSON entries to a temp file for stable iteration and progress
TMP_LIST="$(mktemp)"
trap 'rm -f "$TMP_JSON" "$TMP_LIST"' EXIT
parse_json "$SYSTEM_FILTER" > "$TMP_LIST"

# Build source index once (this can take a moment on first run)
echo -e "${BLUE}${INFO}${RESET} Indexing source BIOS files under: $BIOS_SOURCE_PATH"
build_source_index
total_items=$(wc -l < "$TMP_LIST" | tr -d ' ')
echo -e "${BLUE}${INFO}${RESET} Found ${BOLD}$total_items${RESET} BIOS entries in JSON"

# Helper function to calculate MD5 of a file
get_file_md5() {
  local filepath="$1"
  if [[ -f "$filepath" ]]; then
    md5sum "$filepath" 2>/dev/null | cut -d' ' -f1
  else
    echo ""
  fi
}

# Main loop
while IFS=$'\x1f' read -r bios_name json_path expected_md5; do
  # Determine target dir
  local_target_dir=""
  if [[ -n "$json_path" && "$json_path" != "null" ]]; then
    # Expand variables like $roms_folder/$bios_folder
    expanded=$(expand_vars "$json_path")
    local_target_dir="$expanded"
  else
    local_target_dir="$BIOS_TARGET_PATH"
  fi

  # Guard against MD5 mistakenly used as a directory path
  if is_md5 "$local_target_dir"; then
    echo -e "${YELLOW}${INFO}${RESET} Detected MD5-looking directory path ('$local_target_dir') for $bios_name from json_path='$json_path'. Falling back to BIOS_TARGET_PATH."
    local_target_dir="$BIOS_TARGET_PATH"
  fi

  debug "bios_name='$bios_name' json_path='$json_path' expected_md5='${expected_md5}' resolved_target_dir='$local_target_dir'"

  # Ensure target dir exists
  if [[ ! -d "$local_target_dir" ]]; then
    debug "mkdir -p '$local_target_dir' (cwd=$(pwd))"
    if ! mkdir -p "$local_target_dir" 2>/dev/null; then
      echo -e "${RED}${CROSS}${RESET} Cannot create directory: $local_target_dir (for $bios_name)"
      ((fail_count++))
      continue
    fi
  fi

  dest_path="$local_target_dir/$bios_name"

  # Check if file already exists in destination
  if [[ -f "$dest_path" ]]; then
    if [[ -n "$expected_md5" ]]; then
      dest_md5=$(get_file_md5 "$dest_path")
      if [[ "$dest_md5" == "$expected_md5" ]]; then
        echo -e "${GREEN}${CHECK}${RESET} OK (exists, MD5 OK): $bios_name -> $local_target_dir"
        ((ok_count++)) || true
      else
        echo -e "${RED}${CROSS}${RESET} Exists but MD5 mismatch: $bios_name (expected: $expected_md5, got: $dest_md5)"
        ((fail_count++)) || true
      fi
    else
      echo -e "${GREEN}${CHECK}${RESET} OK (exists, no MD5 check): $bios_name -> $local_target_dir"
      ((ok_count++)) || true
    fi
    ((processed++)) || true
    continue
  fi

  # Find source file - first try by filename, then by MD5 if available
  src_path=""
  key_lookup="${bios_name,,}"
  
  # Try to find by filename first
  if [[ -n "${SOURCE_INDEX[$key_lookup]:-}" ]]; then
    candidate_path="${SOURCE_INDEX[$key_lookup]}"
    if [[ -n "$expected_md5" ]]; then
      candidate_md5=$(get_file_md5 "$candidate_path")
      if [[ "$candidate_md5" == "$expected_md5" ]]; then
        src_path="$candidate_path"
      fi
    else
      # No MD5 to verify, use the file found by name
      src_path="$candidate_path"
    fi
  fi
  
  # If not found by filename or MD5 mismatch, try to find by MD5 hash
  if [[ -z "$src_path" && -n "$expected_md5" ]]; then
    if [[ -n "${MD5_INDEX[$expected_md5]:-}" ]]; then
      src_path="${MD5_INDEX[$expected_md5]}"
      echo -e "${YELLOW}${INFO}${RESET} Found by MD5: $bios_name ($(basename "$src_path"))"
    fi
  fi
  
  # Check if we found a source file
  if [[ -z "$src_path" ]]; then
    if [[ -n "$expected_md5" ]]; then
      echo -e "${RED}${CROSS}${RESET} Missing source: $bios_name (no file with MD5: $expected_md5)"
    else
      echo -e "${RED}${CROSS}${RESET} Missing source: $bios_name (not found under $BIOS_SOURCE_PATH)"
    fi
    ((fail_count++)) || true
    ((processed++)) || true
    if (( processed % 50 == 0 )); then
      echo -e "${YELLOW}${INFO}${RESET} Progress: processed $processed / $total_items"
    fi
    continue
  fi
  
  # Final MD5 verification before copying (if expected MD5 is provided)
  if [[ -n "$expected_md5" ]]; then
    src_md5=$(get_file_md5 "$src_path")
    if [[ "$src_md5" != "$expected_md5" ]]; then
      echo -e "${RED}${CROSS}${RESET} MD5 mismatch: $bios_name (expected: $expected_md5, got: $src_md5)"
      ((fail_count++)) || true
      ((processed++)) || true
      if (( processed % 50 == 0 )); then
        echo -e "${YELLOW}${INFO}${RESET} Progress: processed $processed / $total_items"
      fi
      continue
    fi
  fi

  # Copy the file
  debug "cp -f '$src_path' '$dest_path'"
  if cp -f "$src_path" "$dest_path" 2>/dev/null; then
    if [[ -n "$expected_md5" ]]; then
      echo -e "${GREEN}${CHECK}${RESET} Copied (MD5 OK): $bios_name -> $local_target_dir"
    else
      echo -e "${GREEN}${CHECK}${RESET} Copied: $bios_name -> $local_target_dir"
    fi
    ((ok_count++)) || true
  else
    echo -e "${RED}${CROSS}${RESET} Copy failed: $bios_name (from $src_path to $dest_path)"
    ((fail_count++)) || true
  fi

  ((processed++)) || true
  if (( processed % 50 == 0 )); then
    echo -e "${YELLOW}${INFO}${RESET} Progress: processed $processed / $total_items"
  fi

done < "$TMP_LIST"

# Summary
echo
echo -e "${BOLD}Summary${RESET}"
echo -e "${GREEN}${CHECK}${RESET} OK: $ok_count"
echo -e "${RED}${CROSS}${RESET} Failed/Missing: $fail_count"

exit 0
