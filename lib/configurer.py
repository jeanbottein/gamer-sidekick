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

def resolve_with_missing(value: str, config_vars: dict):
    if not isinstance(value, str):
        return value, []
    variables = re.findall(r'\$\{(\w+)\}', value)
    missing = [var for var in variables if config_vars.get(var) is None and os.getenv(var) is None]
    if missing:
        return None, missing

    def _resolve(m: re.Match) -> str:
        key = m.group(1)
        return config_vars.get(key) or os.getenv(key) or m.group(0)

    return re.sub(r'\$\{(\w+)\}', _resolve, value), []

def normalize_paths(app, raw_paths, config_vars):
    if isinstance(raw_paths, str) or raw_paths is None:
        raw_paths = [raw_paths] if raw_paths is not None else []
    elif not isinstance(raw_paths, list):
        logger.info(f"Skipping {app}: 'paths' must be a list or string. Got: {type(raw_paths).__name__}")
        return []

    resolved_paths = []
    for p in raw_paths:
        resolved_path, missing = resolve_with_missing(p, config_vars)
        if resolved_path is None:
            logger.warning(f"❌ {app} {p} contains undefined variables: {', '.join(missing)}")
            continue
        resolved_paths.append(resolved_path)
    
    if not resolved_paths:
        logger.info(f"❌ {app} no valid paths after variable substitution")
    return resolved_paths

def process_replacements(replacements, config_vars):
    new_replacements = []
    for entry in replacements:
        if isinstance(entry, dict):
            name = entry.get('name', 'unnamed')
            pattern, miss_p = resolve_with_missing(entry.get('pattern', ''), config_vars)
            value, miss_v = resolve_with_missing(entry.get('value', ''), config_vars)
            missing = [*miss_p, *miss_v]
            if missing:
                logger.info(f"❌ {name} replacement contains undefined variables: {', '.join(missing)}")
                continue
            new_replacements.append({'name': name, 'pattern': pattern, 'value': value})
        else:
            try:
                pattern_raw, value_raw = entry
                pattern, miss_p = resolve_with_missing(pattern_raw, config_vars)
                value, miss_v = resolve_with_missing(value_raw, config_vars)
                missing = [*miss_p, *miss_v]
                if missing:
                    logger.info(f"❌ Legacy replacement '{pattern_raw}' contains undefined variables: {', '.join(missing)}")
                    continue
                new_replacements.append({'name': str(pattern_raw), 'pattern': pattern, 'value': value})
            except Exception:
                logger.info(f"❌ Invalid replacement entry: {entry}")
    return new_replacements

def process_hex_replacements(hex_replacements, config_vars):
    new_hex_replacements = []
    for entry in hex_replacements:
        if not isinstance(entry, dict):
            logger.info(f"❌ Invalid hex replacement entry: {entry}")
            continue
            
        name = entry.get('name', 'unnamed')
        hex_pattern, miss_p = resolve_with_missing(entry.get('hex_pattern', ''), config_vars)
        hex_value, miss_v = resolve_with_missing(entry.get('hex_value', ''), config_vars)
        missing = [*miss_p, *miss_v]
        
        if missing:
            logger.info(f"❌ {name} hex replacement contains undefined variables: {', '.join(missing)}")
            continue
            
        hex_entry = {'name': name, 'hex_pattern': hex_pattern, 'hex_value': hex_value}
        new_hex_replacements.append(hex_entry)
    return new_hex_replacements

def load_apps_config(config_vars: dict):
    json_path = Path(__file__).resolve().parent / 'configurer.json'
    with open(json_path, 'r') as json_file:
        apps_config = json.load(json_file)

    for app, config in apps_config.items():
        config['paths'] = normalize_paths(app, config.get('paths'), config_vars)
        config['replacements'] = process_replacements(config.get('replacements', []), config_vars)
        config['hex_replacements'] = process_hex_replacements(config.get('hex_replacements', []), config_vars)
        
        if not config['paths']:
            config['replacements'] = []

    return apps_config

def apply_wildcard_replacement(content, hex_pattern, hex_value, name):
    pattern_parts = hex_pattern.split('??')
    prefix_hex = pattern_parts[0].strip()
    
    prefix_bytes = bytes.fromhex(prefix_hex.replace(' ', ''))
    value_bytes = bytes.fromhex(hex_value.replace(' ', ''))
    
    prefix_pos = content.find(prefix_bytes)
    if prefix_pos == -1:
        logger.info(f"❌ {name} pattern prefix not found")
        return content, False
    
    wildcard_pos = prefix_pos + len(prefix_bytes)
    wildcard_count = hex_pattern.count('??')
    
    if wildcard_pos + wildcard_count > len(content):
        logger.info(f"❌ {name} wildcard position out of bounds")
        return content, False
    
    replacement_bytes = value_bytes[-wildcard_count:] if len(value_bytes) >= wildcard_count else value_bytes
    new_content = content[:wildcard_pos] + replacement_bytes + content[wildcard_pos + wildcard_count:]
    logger.info(f"✅ {name} -> {hex_value}")
    return new_content, True

def apply_exact_replacement(content, hex_pattern, hex_value, name):
    pattern_bytes = bytes.fromhex(hex_pattern.replace(' ', ''))
    value_bytes = bytes.fromhex(hex_value.replace(' ', ''))
    
    if pattern_bytes not in content:
        logger.info(f"❌ {name} pattern not found")
        return content, False
    
    new_content = content.replace(pattern_bytes, value_bytes)
    logger.info(f"✅ {name} -> {hex_value}")
    return new_content, True

def modify_hex_file(file_path, hex_replacements):
    if not file_path or not isinstance(file_path, (str, os.PathLike)) or not os.path.exists(file_path):
        logger.info(f"ℹ️  {file_path} does not exist or invalid path")
        return
    if not hex_replacements:
        logger.info(f"✅ {file_path} no hex replacements to apply")
        return

    logger.info(f"✅ {file_path} detected (binary)")
    
    with open(file_path, 'rb') as file:
        content = file.read()
    
    modified = False
    for rep in hex_replacements:
        if not isinstance(rep, dict):
            logger.info(f"❌ Invalid hex replacement entry: {rep}")
            continue

        name = rep.get('name', 'unnamed')
        hex_pattern = rep.get('hex_pattern', '')
        hex_value = rep.get('hex_value', '')

        try:
            if '??' in hex_pattern:
                content, changed = apply_wildcard_replacement(content, hex_pattern, hex_value, name)
            else:
                content, changed = apply_exact_replacement(content, hex_pattern, hex_value, name)
            modified = modified or changed
        except ValueError as e:
            logger.info(f"❌ {name} invalid hex format: {e}")
    
    if modified:
        with open(file_path, 'wb') as file:
            file.write(content)

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
            logger.info(f"✅ {name} -> {value}")
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
            # Apply normal text replacements if they exist
            if config.get('replacements'):
                modify_file(p, config['replacements'])
            
            # Apply hex replacements if they exist
            if config.get('hex_replacements'):
                modify_hex_file(p, config['hex_replacements'])
