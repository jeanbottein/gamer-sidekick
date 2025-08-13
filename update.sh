#!/bin/bash


SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
rclone="$SCRIPT_DIR/bin/rclone --config $HOME/.config/rclone/rclone.conf"


##### FUNCTIONS ###################################################################################

sync_directories() {
    src_dir=$1
    tgt_dir=$2

    # Attempt bisync
    $rclone bisync "$src_dir" "$tgt_dir" --copy-links --resync-mode path1
    if [ $? -ne 0 ]; then
        echo "Bisync failed, attempting resync..."
        # Attempt resync
        $rclone bisync "$src_dir" "$tgt_dir" --copy-links --resync --resync-mode path1
        if [ $? -ne 0 ]; then
            echo "Resync also failed, performing copy..."
            # Perform copy without destroying
            $rclone copy "$src_dir" "$tgt_dir" --copy-links
        fi
    fi
}


##### MAIN ########################################################################################


sync_directories "${SCRIPT_DIR}" onedrive:Devices/SteamDeck/steamos-pup

echo "Done"
