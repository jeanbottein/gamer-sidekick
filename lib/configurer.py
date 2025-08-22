import json
import os
import re
import logging
from pathlib import Path

logger = logging.getLogger("configurer")

def load_config_file(file_path):
    with open(file_path, 'r') as file:
        lines = (l.strip() for l in file)
        for entry in (l.split('=', 1) for l in lines if l and not l.startswith('#') and '=' in l):
            key, value = entry[0].strip(), entry[1].strip()
            if key and value:
                os.environ[key] = value
            elif key:
                logger.warning(f"Variable '{key}' has an empty value. Skipping.")

def interpret_env(value, config_vars: dict, *, log_level: str = 'warning'):
    if isinstance(value, str):
        resolved, missing = resolve_with_missing(value, config_vars)
        if missing:
            msg = (
                f"Variables {', '.join(missing)} are not defined in config or environment. "
                f"Skipping impacted configuration."
            )
            if log_level == 'info':
                logger.info(msg)
            else:
                logger.warning(msg)
            return None
        return resolved
    return value


def resolve_with_missing(value: str, config_vars: dict):
    if not isinstance(value, str):
        return value, []
    variables = re.findall(r'\$\{(\w+)\}', value)
    missing = [var for var in variables if config_vars.get(var) is None and os.getenv(var) is None]
    if missing:
        return None, missing

    def _resolve(m: re.Match) -> str:
        key = m.group(1)
        if config_vars.get(key) is not None:
            return config_vars[key]
        env_val = os.getenv(key)
        return env_val if env_val is not None else m.group(0)

    return re.sub(r'\$\{(\w+)\}', _resolve, value), []

def load_apps_config(config_vars: dict):
    json_path = Path(__file__).resolve().parent / 'configurer.json'
    with open(json_path, 'r') as json_file:
        apps_config = json.load(json_file)

    for app, config in apps_config.items():
        # Normalize paths: only support 'paths' (list). Legacy 'path' is no longer supported.
        raw_paths = config.get('paths')
        if isinstance(raw_paths, str) or raw_paths is None:
            raw_paths = [raw_paths] if raw_paths is not None else []
        elif not isinstance(raw_paths, list):
            logger.info(f"Skipping {app}: 'paths' must be a list or string. Got: {type(raw_paths).__name__}")
            raw_paths = []

        resolved_paths = []
        for p in raw_paths:
            resolved_path, missing = resolve_with_missing(p, config_vars)
            if resolved_path is None:
                logger.warning(
                    f"❌ {app} {p} contains undefined variables: {', '.join(missing)}"
                )
                continue
            resolved_paths.append(resolved_path)
        if not resolved_paths:
            logger.info(f"❌ {app} no valid paths after variable substitution")
            config['replacements'] = []
        # Store normalized list under 'paths' for downstream use
        config['paths'] = resolved_paths

        new_replacements = []
        for entry in config['replacements']:
            if isinstance(entry, dict):
                name = entry.get('name', 'unnamed')
                pattern, miss_p = resolve_with_missing(entry.get('pattern', ''), config_vars)
                value, miss_v = resolve_with_missing(entry.get('value', ''), config_vars)
                missing = [*miss_p, *miss_v]
                if missing:
                    logger.info(
                        f"❌ {name} replacement contains undefined variables: {', '.join(missing)}"
                    )
                    continue
                new_replacements.append({'name': name, 'pattern': pattern, 'value': value})
            else:
                try:
                    pattern_raw, value_raw = entry
                except Exception:
                    logger.info(f"❌ Invalid replacement entry: {entry}")
                    continue
                pattern, miss_p = resolve_with_missing(pattern_raw, config_vars)
                value, miss_v = resolve_with_missing(value_raw, config_vars)
                missing = [*miss_p, *miss_v]
                if missing:
                    logger.info(
                        f"❌ Legacy replacement '{pattern_raw}' contains undefined variables: {', '.join(missing)}"
                    )
                    continue
                new_replacements.append({'name': str(pattern_raw), 'pattern': pattern, 'value': value})
        config['replacements'] = new_replacements

    return apps_config

def modify_file(file_path, replacements):
    if not file_path or not isinstance(file_path, (str, os.PathLike)):
        logger.info("🤖 No valid path provided; skipping modifications.")
        return
    if not os.path.exists(file_path):
        logger.info(f"ℹ️  {file_path} does not exist")
        return
    if not replacements:
        logger.info(f"✅ {file_path} no replacements to apply")
        return

    logger.info(f"✅ {file_path} detected")
    with open(file_path, 'r') as file:
        content = file.read()
    modified = False
    for rep in replacements:
        if isinstance(rep, dict):
            name = rep.get('name', 'unnamed')
            pattern = rep.get('pattern', '')
            value = rep.get('value', '')
        else:
            try:
                pattern, value = rep
            except Exception:
                logger.info(f"❌ Invalid replacement entry: {rep}")
                continue
            name = str(pattern)

        if re.search(pattern, content):
            content = re.sub(pattern, value, content)
            logger.info(f"✅ {name} set")
            modified = True
    if modified:
        with open(file_path, 'w') as file:
            file.write(content)


def run(config_vars: dict):
    apps_config = load_apps_config(config_vars)

    for app_name, config in apps_config.items():
        # Use normalized 'paths' only
        paths = config.get('paths')
        if not paths:
            logger.info(f"❌ {app_name} no paths defined after variable substitution")
            continue
        logger.info(f"🤖 Configuring {app_name}...")
        for p in paths:
            modify_file(p, config['replacements'])
