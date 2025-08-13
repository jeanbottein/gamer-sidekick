import os
import json
from dotenv import load_dotenv

def load_config():
    load_dotenv()
    with open('symlinks.json', 'r') as f:
        return json.load(f)

def expand_path(path):
    # Expand environment variables and user home directory
    expanded_path = os.path.expandvars(os.path.expanduser(path))
    # Convert to absolute path
    return os.path.abspath(expanded_path)

def create_symlink(src_dir, tgt_dir):
    # Convert paths to absolute
    src_dir = expand_path(src_dir)
    tgt_dir = expand_path(tgt_dir)

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

def create_symlinks():
    config = load_config()
    for symlink in config['symlinks']:
        create_symlink(symlink['src'], symlink['tgt'])

if __name__ == "__main__":
    create_symlinks()
    print("Done")
