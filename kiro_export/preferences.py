"""Persistence for non-sensitive exporter UI preferences."""

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict

from .options import ExportOptions
from .sections import ALL_SECTION_KEYS, ORCH_LAYERS, ORCH_STATUSES, SECTION_DEFS


_DEFAULT_SECTIONS = {key: on for key, _label, _emoji, on in SECTION_DEFS}
_ORCH_STATUS_KEYS = {key for key, _label in ORCH_STATUSES}
_ORCH_LAYER_KEYS = {key for key, _label, _on in ORCH_LAYERS}
_DEFAULT_ORCH_FILTER = {
    'statuses': {key: True for key, _label in ORCH_STATUSES},
    'layers': {key: on for key, _label, on in ORCH_LAYERS},
    'latest_only': False,
}
_DEFAULTS = {
    'source': 'ide',
    'format': 'markdown',
    'destination': 'f',
    'output_location': 'project',
    'file_mode': 'separate',
    'scope': {'mode': 'full'},
    'export_options': ExportOptions(sections=_DEFAULT_SECTIONS,
                                    orch_filter=_DEFAULT_ORCH_FILTER).as_dict(),
}
_ENUMS = {
    'source': {'ide', 'cli'},
    'format': {'json', 'markdown'},
    'destination': {'f', 'c', 'b'},
    'output_location': {'project', 'script'},
    'file_mode': {'combined', 'separate'},
}
_ALLOWED_KEYS = frozenset(_DEFAULTS)


def preferences_path() -> Path:
    """Return the current config location, honoring the environment each call."""
    override = os.environ.get('KIRO_EXPORT_CONFIG')
    if override:
        return Path(override).expanduser()
    if os.name == 'nt':
        base = os.environ.get('APPDATA')
        if base:
            return Path(base) / 'kiro-session-export' / 'settings.json'
    xdg = os.environ.get('XDG_CONFIG_HOME')
    base_path = Path(xdg).expanduser() if xdg else Path.home() / '.config'
    return base_path / 'kiro-session-export' / 'settings.json'


def _valid_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _clean_scope(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return dict(_DEFAULTS['scope'])
    mode = value.get('mode')
    if not isinstance(mode, str) or mode not in {'full', 'first', 'last', 'range', 'live'}:
        return dict(_DEFAULTS['scope'])
    if mode in {'first', 'last'}:
        n = value.get('n')
        return {'mode': mode, 'n': n} if _valid_nonnegative_int(n) and n >= 1 else dict(_DEFAULTS['scope'])
    if mode == 'range':
        start, end = value.get('start'), value.get('end')
        if (_valid_nonnegative_int(start) and _valid_nonnegative_int(end)
                and start >= 1 and end >= 1 and start <= end):
            return {'mode': mode, 'start': start, 'end': end}
        return dict(_DEFAULTS['scope'])
    return {'mode': mode}


def _clean_options(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return ExportOptions.from_dict(_DEFAULTS['export_options']).as_dict()
    sections = value.get('sections', _DEFAULT_SECTIONS)
    if (not isinstance(sections, dict)
            or any(not isinstance(key, str) or not isinstance(flag, bool)
                   for key, flag in sections.items())):
        sections = _DEFAULT_SECTIONS
    else:
        sections = {key: flag for key, flag in sections.items()
                    if key in ALL_SECTION_KEYS}
    orch = value.get('orch_filter', _DEFAULT_ORCH_FILTER)
    if not isinstance(orch, dict):
        orch = _DEFAULT_ORCH_FILTER
    statuses = orch.get('statuses', {})
    layers = orch.get('layers', {})
    if not isinstance(statuses, dict):
        statuses = {}
    if not isinstance(layers, dict):
        layers = {}
    clean_statuses = {key: flag for key, flag in statuses.items()
                      if isinstance(key, str) and key in _ORCH_STATUS_KEYS
                      and isinstance(flag, bool)}
    clean_layers = {key: flag for key, flag in layers.items()
                    if isinstance(key, str) and key in _ORCH_LAYER_KEYS
                    and isinstance(flag, bool)}
    latest = orch.get('latest_only', False)
    orch = {'statuses': clean_statuses, 'layers': clean_layers,
            'latest_only': latest if isinstance(latest, bool) else False}
    cleaned = dict(value)
    cleaned['sections'] = sections
    cleaned['orch_filter'] = orch
    return ExportOptions.from_dict(cleaned).as_dict()


def _clean_preferences(value: Any) -> Dict[str, Any]:
    result = {
        'source': _DEFAULTS['source'], 'format': _DEFAULTS['format'],
        'destination': _DEFAULTS['destination'],
        'output_location': _DEFAULTS['output_location'],
        'file_mode': _DEFAULTS['file_mode'],
        'scope': dict(_DEFAULTS['scope']),
        'export_options': ExportOptions.from_dict(_DEFAULTS['export_options']).as_dict(),
    }
    if not isinstance(value, dict):
        return result
    for key, allowed in _ENUMS.items():
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate in allowed:
            result[key] = candidate
    result['scope'] = _clean_scope(value.get('scope'))
    result['export_options'] = _clean_options(value.get('export_options'))
    return result


def load_preferences() -> dict:
    """Read and validate preferences; missing or malformed files use defaults."""
    try:
        raw = json.loads(preferences_path().read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raw = {}
    return _clean_preferences(raw)


def save_preferences(data: dict) -> bool:
    """Atomically save whitelisted preferences, merging a partial update."""
    if not isinstance(data, dict):
        return False
    temp_path = None
    try:
        path = preferences_path()
        try:
            previous_raw = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            previous_raw = {}
        merged = _clean_preferences(previous_raw)
        for key in _ALLOWED_KEYS:
            if key in data:
                incoming = data[key]
                if key == 'export_options' and isinstance(incoming, dict):
                    options = dict(merged['export_options'])
                    for option_key, option_value in incoming.items():
                        if option_key == 'sections' and isinstance(option_value, dict):
                            sections = dict(options.get('sections', {}))
                            sections.update(option_value)
                            options[option_key] = sections
                        elif option_key == 'orch_filter' and isinstance(option_value, dict):
                            orch = dict(options.get('orch_filter', {}))
                            for filter_key, filter_value in option_value.items():
                                if filter_key in ('statuses', 'layers') and isinstance(filter_value, dict):
                                    current = dict(orch.get(filter_key, {}))
                                    current.update(filter_value)
                                    orch[filter_key] = current
                                else:
                                    orch[filter_key] = filter_value
                            options[option_key] = orch
                        else:
                            options[option_key] = option_value
                    merged[key] = options
                else:
                    merged[key] = incoming
        payload = _clean_preferences(merged)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=str(path.parent),
                                         prefix=path.name + '.', suffix='.tmp',
                                         delete=False) as stream:
            temp_path = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp_path), str(path))
        return True
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
