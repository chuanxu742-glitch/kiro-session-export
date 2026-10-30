"""Non-interactive command line interface for session export."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PureWindowsPath
from typing import Optional

from .options import ExportOptions


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _parser():
    parser = _ArgumentParser(prog='kiro-export', description='List and export Kiro sessions.')
    commands = parser.add_subparsers(dest='command')
    listing = commands.add_parser('list', help='List sessions')
    listing.add_argument('--source', choices=('ide', 'cli', 'all'))
    listing.add_argument('--workspace')
    listing.add_argument('--json', action='store_true', dest='as_json')

    export = commands.add_parser('export', help='Export one or more sessions')
    export.add_argument('--source', choices=('ide', 'cli'))
    export.add_argument('--session', action='append', required=True, metavar='ID')
    export.add_argument('--format', choices=('json', 'markdown'))
    export.add_argument('--output', type=Path)
    export.add_argument('--preset', choices=('default', 'chat', 'full'), default='default')
    scopes = export.add_mutually_exclusive_group()
    scopes.add_argument('--last', type=int)
    scopes.add_argument('--first', type=int)
    scopes.add_argument('--turns', metavar='START:END')
    scopes.add_argument('--live', action='store_true')
    export.add_argument('--output-cap', type=int)
    export.add_argument('--clean-chat', action='store_true')
    export.add_argument('--combine', action='store_true')
    export.add_argument('--reuse', action='store_true')
    return parser


def _pref(prefs, key, default=None):
    return prefs.get(key, default) if isinstance(prefs, dict) else default


def _source(runtime, source):
    if source == 'cli':
        return list(runtime.scan_cli_sessions())
    if source == 'all':
        ide = list(runtime.scan_all_sessions())
        cli = list(runtime.scan_cli_sessions())
        return [(entry, 'ide') for entry in ide] + [(entry, 'cli') for entry in cli]
    return list(runtime.scan_all_sessions())


def _list(runtime, args, prefs):
    source = args.source or _pref(prefs, 'source', 'ide')
    if source not in ('ide', 'cli', 'all'):
        source = 'ide'
    entries = _source(runtime, source)
    if source != 'all':
        entries = [(entry, source) for entry in entries]
    if args.workspace:
        wanted = runtime._norm_ws_path(args.workspace)
        entries = [(entry, origin) for entry, origin in entries
                   if runtime._norm_ws_path(getattr(entry, 'workspace_dir', '') or '') == wanted]
    rows = []
    for entry, origin in entries:
        rows.append({
            'session_id': entry.session_id,
            'source': origin,
            'title': getattr(entry, 'display_title', None) or getattr(entry, 'title', '') or '',
            'workspace': getattr(entry, 'workspace_dir', '') or '',
            'date_created': getattr(entry, 'date_created', 0) or 0,
        })
    if args.as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row['source']}\t{row['session_id']}\t{row['title']}\t{row['workspace']}")
    return 0


def _scope(runtime, args, prefs=None):
    if args.last is not None:
        if args.last < 1:
            raise ValueError('--last must be at least 1')
        return runtime._last_scope(args.last)
    if args.first is not None:
        if args.first < 1:
            raise ValueError('--first must be at least 1')
        return runtime._first_scope(args.first)
    if args.turns:
        match = re.fullmatch(r'(\d+):(\d+)', args.turns)
        if not match:
            raise ValueError('--turns must use START:END')
        start, end = map(int, match.groups())
        if start < 1 or end < start:
            raise ValueError('--turns requires 1 <= START <= END')
        return runtime._range_scope(start, end)
    if args.live:
        return runtime._live_scope()
    saved = _pref(prefs, 'scope') if args.reuse else None
    if isinstance(saved, dict) and saved.get('mode') in ('full', 'last', 'first', 'range', 'live'):
        mode = saved['mode']
        if mode in ('last', 'first') and int(saved.get('n', 0)) < 1:
            raise ValueError('saved scope requires a positive turn count')
        if mode == 'range' and (int(saved.get('start', 0)) < 1 or
                                int(saved.get('end', 0)) < int(saved.get('start', 0))):
            raise ValueError('saved scope requires 1 <= START <= END')
        return saved
    return runtime._full_scope()


def _choose_entries(runtime, args, prefs):
    source = args.source or _pref(prefs, 'source', 'ide')
    if source not in ('ide', 'cli'):
        source = 'ide'
    entries = _source(runtime, source)
    chosen = []
    errors = []
    seen = set()
    for query in args.session:
        q = query.strip().lower()
        exact = [entry for entry in entries if str(entry.session_id).lower() == q]
        matches = exact or [entry for entry in entries if str(entry.session_id).lower().startswith(q)]
        if len(matches) != 1:
            errors.append(f"session ID {query!r}: " + ('not found' if not matches else 'ambiguous'))
            continue
        entry = matches[0]
        if entry.session_id not in seen:
            seen.add(entry.session_id)
            chosen.append(entry)
    if errors:
        raise LookupError('; '.join(errors))
    return source, chosen


def _options(runtime, args, prefs):
    getter = getattr(runtime, 'get_default_export_options', None)
    options = (getter() if callable(getter) else
               ExportOptions(sections={key: True for key in
                                       getattr(runtime, 'ALL_SECTION_KEYS', ())}))
    if args.reuse:
        saved = _pref(prefs, 'export_options', {})
        if isinstance(saved, dict):
            for name in ('sections', 'clean_content', 'output_cap', 'user_cap', 'agent_cap',
                         'reasoning_cap', 'summary_cap', 'orch_filter'):
                if name in saved and hasattr(options, name):
                    setattr(options, name, saved[name])
    keys = list(getattr(runtime, 'ALL_SECTION_KEYS', options.sections.keys()))
    if args.preset == 'full':
        options.sections = {key: True for key in keys}
    elif args.preset == 'chat':
        options.sections = {key: key in ('user_message', 'agent_message') for key in keys}
    if args.output_cap is not None:
        if args.output_cap < 0:
            raise ValueError('--output-cap must be zero or greater')
        options.output_cap = args.output_cap
    if args.clean_chat:
        options.clean_content = True
    return options


def _safe_basename(filename):
    value = str(filename)
    if (not value or value in ('.', '..') or Path(value).name != value
            or PureWindowsPath(value).name != value):
        raise ValueError(f'unsafe export filename: {value!r}')
    return value


def _session_filename(runtime, session_id):
    cleaner = getattr(runtime, 'clean_filename', None)
    candidate = cleaner(str(session_id)) if callable(cleaner) else str(session_id)
    return _safe_basename(candidate)


def _export(runtime, args, prefs):
    source, entries = _choose_entries(runtime, args, prefs)
    if not entries:
        raise LookupError('No sessions selected')
    options = _options(runtime, args, prefs)
    scope = _scope(runtime, args, prefs)
    parser_cls = runtime.CliSessionParser if source == 'cli' else runtime.SessionParser
    # Legacy IDE records point at <session-id>.json and need the execution index;
    # modern records use session.json and already contain their message stream.
    if source == 'ide' and any(getattr(entry, 'session_file', None) and
                               Path(entry.session_file).name != 'session.json' for entry in entries):
        runtime.EXEC_INDEX = runtime.ExecutionIndex(runtime.KIRO_HOME)
        runtime.EXEC_INDEX.build()
    parsers = runtime._parse_sessions_parallel(entries, parser_cls=parser_cls)
    if not parsers or len(parsers) != len(entries) or any(parsed is None for parsed in parsers):
        raise RuntimeError(f'Could not parse all selected sessions ({len(parsers or [])}/{len(entries)})')
    filenames = [_session_filename(runtime, parsed.session_id) for parsed in parsers]
    for parsed in parsers:
        runtime.apply_extraction_scope(parsed, scope)
    fmt = args.format or _pref(prefs, 'format', 'markdown')
    if fmt not in ('json', 'markdown'):
        fmt = 'markdown'
    output = args.output or Path.cwd()
    output.mkdir(parents=True, exist_ok=True)
    kwargs = options.render_kwargs()
    if args.combine:
        if fmt == 'json':
            content, filename = runtime.combine_parsers_to_json(parsers, options.sections,
                options.clean_content, options.output_cap, options.user_cap, options.agent_cap,
                options.reasoning_cap, options.summary_cap, options.orch_filter)
        else:
            content, filename = runtime.combine_parsers_to_markdown(parsers, options.sections,
                options.clean_content, options.output_cap, options.user_cap, options.agent_cap,
                options.reasoning_cap, options.summary_cap, options.orch_filter)
        written = runtime.write_export_file(output / _safe_basename(filename), content)
        print(f'Saved: {written}')
        return 0
    suffix = '.json' if fmt == 'json' else '.md'
    for parsed, basename in zip(parsers, filenames):
        content = parsed.to_json(**kwargs) if fmt == 'json' else parsed.to_markdown(**kwargs)
        written = runtime.write_export_file(output / f'{basename}{suffix}', content)
        print(f'Saved: {written}')
    return 0


def run_cli(runtime, argv=None) -> Optional[int]:
    """Run CLI commands against an injected runtime.

    Returns ``None`` when the caller should continue in interactive mode,
    otherwise an exit code: 0 for success/help, 1 for runtime failures, or
    2 for invalid arguments and session selections.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return None
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        if args.command is None:
            parser.print_help()
            return 0
        prefs = runtime.load_preferences()
        if args.command == 'list':
            return _list(runtime, args, prefs)
        return _export(runtime, args, prefs)
    except SystemExit as exc:
        return int(exc.code or 0)
    except (ValueError, LookupError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
