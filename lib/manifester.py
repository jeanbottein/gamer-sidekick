import os
import json
import subprocess
import difflib
import logging

logger = logging.getLogger("manifester")

relative_path = True

manifest_filename= "launch_manifest.json"
manifests_filename= "manifests.json"

def run_find_exe(cmd):
    try:
        executables = subprocess.check_output(cmd, shell=True, text=True).splitlines()
    except subprocess.CalledProcessError:
        return None
    if not executables:
        return None
    return executables

def find_best(game_dir, files):
    if files is None:
        return None
    if len(files) == 1:
        return files[0]

    folder_base = os.path.basename(game_dir)
    best_match = None
    highest_score = 0.0

    for file in files:
        file_base = os.path.splitext(os.path.basename(file))[0]
        score = difflib.SequenceMatcher(None, folder_base, file_base).ratio()
        if score > highest_score:
            highest_score = score
            best_match = file

    return best_match

def get_bin(game_dir, maxdepth, filter=""):
    cmd = f"""find "{game_dir}" -maxdepth {maxdepth} -type f -executable -exec file {{}} + | \
        grep executable | grep "{filter}"  | sed "s#:.*##" | \
        grep -v "/java/" | grep -v "/jre/" | grep -v "/lib/" """
    return find_best(game_dir,run_find_exe(cmd))

def get_target(game_dir):
    real_game_dir=get_real_first_path(game_dir)
    filters = ["x86-64", "x86", ""]  # Order of preference
    for depth in range(1, 4):  # max depth of 3
        for filter in filters:
            exe = get_bin(real_game_dir, depth, filter)
            if exe is not None:
                return exe

    return None

def format_path(full_path, base_path):
    if relative_path:
        return os.path.relpath(full_path, base_path)
    return full_path

def get_real_first_path(game_dir):
    game_dir = os.path.normpath(game_dir)
    entries = [entry for entry in os.listdir(game_dir) if not entry.startswith('.') and entry != manifest_filename]

    # Filter out directories and files
    directories = [entry for entry in entries if os.path.isdir(os.path.join(game_dir, entry))]
    files = [entry for entry in entries if os.path.isfile(os.path.join(game_dir, entry))]

    if len(directories) == 1 and len(files) == 0:
        return get_real_first_path(os.path.join(game_dir, directories[0]))

    return game_dir

def get_title(game_dir):
    return os.path.basename(get_real_first_path(game_dir))


def write_manifest(manifest_path, manifest):
    try:
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=4)
        logger.info(f"✅ {os.path.basename(os.path.dirname(manifest_path))} manifest created")
    except Exception as e:
        logger.error(f"❌ Error creating manifest in {os.path.basename(os.path.dirname(manifest_path))}: {str(e)}")


def createManifest(game_dir):
    manifest_path = os.path.join(game_dir, manifest_filename)
    if(os.path.exists(manifest_path)):
        return
    target = get_target(game_dir)
    if target is None:
        logger.info(f"❌ {os.path.basename(game_dir)} no executable found")
        return None
    logger.info(f"✅ {os.path.basename(game_dir)} executable detected")
    manifest = {
        "title": get_title(game_dir),
        "target": format_path(target,game_dir),
        "startIn": format_path(os.path.dirname(target),game_dir),
        "launchOptions": ""
    }

    write_manifest(manifest_path, manifest)


def find_manifests(game_dir):
    manifests = []
    for root, dirs, files in os.walk(game_dir):
        if manifest_filename in files:
            manifest_path = os.path.join(root, manifest_filename)
            manifests.append(manifest_path)
    return manifests

def load_and_ajust_manifest(manifest_path):
    subfolder = os.path.dirname(manifest_path)
    with open(manifest_path, 'r') as f:
        manifest=json.load(f)
        if 'target' in manifest:
            manifest['target'] = os.path.normpath(os.path.join(subfolder, manifest['target']))
        if 'startIn' in manifest:
            manifest['startIn'] = os.path.normpath(os.path.join(subfolder, manifest['startIn']))
        return manifest

def create_main_manifest(games_dir):
    manifests = find_manifests(games_dir)
    main_manifest = []
    for manifest_path in manifests:
        manifest = load_and_ajust_manifest(manifest_path)
        main_manifest.append(manifest)
        logger.info(f"✅ {manifest['title']}")

    main_manifest_path = os.path.join(games_dir, manifests_filename)
    with open(main_manifest_path, 'w') as f:
        json.dump(main_manifest, f, indent=4)

    logger.info(f"✅ Manifests file created at: {main_manifest_path}")

def run(config: dict):
    games_dir = config.get('FREEGAMES_PATH') or os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), 'games'
    )

    if not os.path.isdir(games_dir):
        logger.warning(f"❌ {games_dir} is not a valid directory")
        return

    logger.info(f"🤖 looking for games in {games_dir}")
    for item in os.listdir(games_dir):
        item_path = os.path.join(games_dir, item)
        if os.path.isdir(item_path):
            createManifest(item_path)

    create_main_manifest(games_dir)
