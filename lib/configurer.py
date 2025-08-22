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
            replacement_type = entry.get('type', 'text')  # Default to text
            pattern, miss_p = resolve_with_missing(entry.get('pattern', ''), config_vars)
            value, miss_v = resolve_with_missing(entry.get('value', ''), config_vars)
            missing = [*miss_p, *miss_v]
            if missing:
                logger.info(f"❌ {name} replacement contains undefined variables: {', '.join(missing)}")
                continue
            new_replacements.append({
                'name': name, 
                'pattern': pattern, 
                'value': value, 
                'type': replacement_type
            })
        else:
            try:
                pattern_raw, value_raw = entry
                pattern, miss_p = resolve_with_missing(pattern_raw, config_vars)
                value, miss_v = resolve_with_missing(value_raw, config_vars)
                missing = [*miss_p, *miss_v]
                if missing:
                    logger.info(f"❌ Legacy replacement '{pattern_raw}' contains undefined variables: {', '.join(missing)}")
                    continue
                new_replacements.append({
                    'name': str(pattern_raw), 
                    'pattern': pattern, 
                    'value': value, 
                    'type': 'text'
                })
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

    processed_config = {}
    for app, config in apps_config.items():
        files = config.get('files', [])
        processed_files = []
        
        for file_config in files:
            processed_file = {}
            processed_file['paths'] = normalize_paths(app, file_config.get('paths'), config_vars)
            processed_file['replacements'] = process_replacements(file_config.get('replacements', []), config_vars)
            processed_file['hex_replacements'] = process_hex_replacements(file_config.get('hex_replacements', []), config_vars)
            
            if not processed_file['paths']:
                processed_file['replacements'] = []
                processed_file['hex_replacements'] = []
            
            processed_files.append(processed_file)
        
        processed_config[app] = {'files': processed_files}

    return processed_config

def apply_wildcard_replacement(content, hex_pattern, hex_value, name):
    # Find the pattern by replacing ?? with any byte
    pattern_parts = hex_pattern.split('??')
    if len(pattern_parts) != 2:
        logger.info(f"❌ {name} invalid wildcard pattern (must have exactly one ??)")
        return content, False
    
    prefix_hex = pattern_parts[0].strip()
    suffix_hex = pattern_parts[1].strip()
    
    prefix_bytes = bytes.fromhex(prefix_hex.replace(' ', '')) if prefix_hex else b''
    suffix_bytes = bytes.fromhex(suffix_hex.replace(' ', '')) if suffix_hex else b''
    value_bytes = bytes.fromhex(hex_value.replace(' ', ''))
    
    # Find the pattern in the content
    pattern_length = len(prefix_bytes) + 1 + len(suffix_bytes)  # +1 for the wildcard byte
    
    for i in range(len(content) - pattern_length + 1):
        # Check if prefix matches
        if prefix_bytes and content[i:i+len(prefix_bytes)] != prefix_bytes:
            continue
        
        # Check if suffix matches (after the wildcard byte)
        suffix_start = i + len(prefix_bytes) + 1
        if suffix_bytes and content[suffix_start:suffix_start+len(suffix_bytes)] != suffix_bytes:
            continue
        
        # Found the pattern, replace the entire pattern with the new value
        new_content = content[:i] + value_bytes + content[i + pattern_length:]
        
        # Add ASCII interpretation for logging
        ascii_interpretation = ""
        try:
            # Try to decode the hex value as ASCII for display
            ascii_chars = []
            hex_bytes = bytes.fromhex(hex_value.replace(' ', ''))
            for byte in hex_bytes:
                if 32 <= byte <= 126:  # Printable ASCII range
                    ascii_chars.append(chr(byte))
                else:
                    ascii_chars.append(str(byte))
            ascii_interpretation = ''.join(ascii_chars)
        except:
            ascii_interpretation = hex_value
        
        logger.info(f"✅ {name} -> {ascii_interpretation}")
        return new_content, True
    
    logger.info(f"❌ {name} pattern not found")
    return content, False

def apply_exact_replacement(content, hex_pattern, hex_value, name):
    pattern_bytes = bytes.fromhex(hex_pattern.replace(' ', ''))
    value_bytes = bytes.fromhex(hex_value.replace(' ', ''))
    
    if pattern_bytes not in content:
        logger.info(f"❌ {name} pattern not found")
        return content, False
    
    new_content = content.replace(pattern_bytes, value_bytes)
    
    # Add ASCII interpretation for logging
    ascii_interpretation = ""
    try:
        # Try to decode the hex value as ASCII for display
        ascii_chars = []
        hex_bytes = bytes.fromhex(hex_value.replace(' ', ''))
        for byte in hex_bytes:
            if 32 <= byte <= 126:  # Printable ASCII range
                ascii_chars.append(chr(byte))
            else:
                ascii_chars.append(str(byte))
        ascii_interpretation = ''.join(ascii_chars)
    except:
        ascii_interpretation = hex_value
    
    logger.info(f"✅ {name} -> {ascii_interpretation}")
    return new_content, True

def convert_decimal_to_hex_in_value(value):
    """Convert decimal numbers in ASCII value to hex bytes"""
    import re
    
    def replace_decimal(match):
        decimal_str = match.group(1)
        try:
            decimal_val = int(decimal_str)
            if 0 <= decimal_val <= 255:
                return f"{decimal_val:02x}"
            else:
                logger.info(f"❌ Decimal value {decimal_val} out of range (0-255)")
                return decimal_str
        except ValueError:
            return decimal_str
    
    # Replace ${VAR} that resolved to decimal numbers with hex
    # Look for patterns like IPL.LNG3 and convert the 3 to 03
    result = ""
    i = 0
    while i < len(value):
        char = value[i]
        if char.isdigit():
            # Found a digit, collect consecutive digits
            num_str = ""
            while i < len(value) and value[i].isdigit():
                num_str += value[i]
                i += 1
            # Convert to hex byte
            try:
                decimal_val = int(num_str)
                if 0 <= decimal_val <= 255:
                    result += f"{decimal_val:02x}"
                else:
                    result += num_str
            except ValueError:
                result += num_str
        else:
            result += char
            i += 1
    
    return result

def ascii_to_hex_pattern(ascii_pattern):
    """Convert ASCII pattern with ? wildcards to hex pattern with ?? wildcards"""
    hex_parts = []
    for char in ascii_pattern:
        if char == '?':
            hex_parts.append('??')
        else:
            hex_parts.append(f"{ord(char):02x}")
    return ' '.join(hex_parts)

def ascii_to_hex_value(ascii_value):
    """Convert ASCII value to hex, handling decimal numbers"""
    # First convert any decimal numbers to hex
    processed_value = convert_decimal_to_hex_in_value(ascii_value)
    
    # Then convert ASCII chars to hex
    hex_parts = []
    i = 0
    while i < len(processed_value):
        if i + 1 < len(processed_value) and all(c in '0123456789abcdefABCDEF' for c in processed_value[i:i+2]):
            # This looks like a hex byte
            hex_parts.append(processed_value[i:i+2])
            i += 2
        else:
            # Regular ASCII character
            hex_parts.append(f"{ord(processed_value[i]):02x}")
            i += 1
    
    return ' '.join(hex_parts)

def modify_hex_file_with_ascii(file_path, replacements):
    """Handle hexadecimal replacements using ASCII patterns"""
    if not file_path or not isinstance(file_path, (str, os.PathLike)) or not os.path.exists(file_path):
        logger.info(f"ℹ️  {file_path} does not exist or invalid path")
        return
    if not replacements:
        logger.info(f"✅ {file_path} no hex replacements to apply")
        return

    logger.info(f"✅ {file_path} detected (binary)")
    
    with open(file_path, 'rb') as file:
        content = file.read()
    
    modified = False
    for rep in replacements:
        if not isinstance(rep, dict):
            logger.info(f"❌ Invalid hex replacement entry: {rep}")
            continue

        name = rep.get('name', 'unnamed')
        ascii_pattern = rep.get('pattern', '')
        ascii_value = rep.get('value', '')

        try:
            # Convert ASCII patterns to hex
            hex_pattern = ascii_to_hex_pattern(ascii_pattern)
            hex_value = ascii_to_hex_value(ascii_value)
            
            # Use existing hex replacement logic
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
        files = config.get('files', [])
        if not files:
            logger.info(f"❌ {app_name} no files defined")
            continue
            
        logger.info(f"🤖 Configuring {app_name}...")
        
        for file_config in files:
            paths = file_config.get('paths', [])
            if not paths:
                continue
                
            for p in paths:
                # Apply replacements based on type
                if file_config.get('replacements'):
                    for replacement in file_config['replacements']:
                        if replacement.get('type') == 'hexadecimal':
                            modify_hex_file_with_ascii(p, [replacement])
                        else:
                            modify_file(p, [replacement])
                
                # Apply hex replacements if they exist (legacy support)
                if file_config.get('hex_replacements'):
                    modify_hex_file(p, file_config['hex_replacements'])
