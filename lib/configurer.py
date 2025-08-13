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
        resolved_path, missing = resolve_with_missing(config['path'], config_vars)
        config['path'] = resolved_path
        if config['path'] is None:
            logger.warning(
                f"Skipping {app}: path contains undefined variables: {', '.join(missing)}."
            )
            config['replacements'] = []
            continue

        new_replacements = []
        for entry in config['replacements']:
            if isinstance(entry, dict):
                name = entry.get('name', 'unnamed')
                pattern, miss_p = resolve_with_missing(entry.get('pattern', ''), config_vars)
                value, miss_v = resolve_with_missing(entry.get('value', ''), config_vars)
                missing = [*miss_p, *miss_v]
                if missing:
                    logger.info(
                        f"Skipping replacement '{name}': undefined variables: {', '.join(missing)}."
                    )
                    continue
                new_replacements.append({'name': name, 'pattern': pattern, 'value': value})
            else:
                try:
                    pattern_raw, value_raw = entry
                except Exception:
                    logger.info(f"Skipping invalid replacement entry: {entry}")
                    continue
                pattern, miss_p = resolve_with_missing(pattern_raw, config_vars)
                value, miss_v = resolve_with_missing(value_raw, config_vars)
                missing = [*miss_p, *miss_v]
                if missing:
                    logger.info(
                        f"Skipping legacy replacement '{pattern_raw}': undefined variables: {', '.join(missing)}."
                    )
                    continue
                new_replacements.append({'name': str(pattern_raw), 'pattern': pattern, 'value': value})
        config['replacements'] = new_replacements

    return apps_config

def modify_file(file_path, replacements):
    if not file_path or not isinstance(file_path, (str, os.PathLike)):
        logger.info("No valid path provided; skipping modifications.")
        return
    if not os.path.exists(file_path):
        logger.warning(f"File {file_path} does not exist.")
        return
    if not replacements:
        logger.info(f"No replacements to apply for file {file_path}. Skipping.")
        return

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
                logger.info(f"Skipping invalid replacement entry: {rep}")
                continue
            name = str(pattern)

        if re.search(pattern, content):
            content = re.sub(pattern, value, content)
            logger.info(f"[{name}] Replaced pattern in file {file_path}.")
            modified = True
    if modified:
        with open(file_path, 'w') as file:
            file.write(content)
        logger.info(f"Modified file {file_path} successfully.")
    else:
        logger.info(f"No changes made to file {file_path}.")


def run(config_vars: dict):
    apps_config = load_apps_config(config_vars)

    for app_name, config in apps_config.items():
        path = config.get('path')
        if not path:
            logger.info(f"Skipping {app_name}: path undefined after variable substitution.")
            continue
        logger.info(f"Configuring {app_name}...")
        modify_file(path, config['replacements'])
