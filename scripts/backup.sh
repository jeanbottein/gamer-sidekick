#!/usr/bin/env bash
set -euo pipefail

RCLONE="/home/deck/sd/apps/gamer-sidekick/bin/rclone"
REMOTE="ludusavi-1763680370"

SRC1="/run/media/deck/SteamDeck-SD/gamer-sidekick-backup"
DST1="Machines/SteamDeck/gamer-sidekick-backup"

SRC2="/run/media/deck/SteamDeck-SD/linux-games"
DST2="Machines/SteamDeck/games"

"$RCLONE" copy "$SRC1" "${REMOTE}:${DST1}" --progress
"$RCLONE" copy "$SRC2" "${REMOTE}:${DST2}" --progress
