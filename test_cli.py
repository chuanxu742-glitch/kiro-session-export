from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from kiro_export.cli import run_cli


@dataclass
class Options:
    sections: dict
    clean_content: bool = False
    output_cap: int = 0
    user_cap: int = 0
    agent_cap: int = 0
    reasoning_cap: int = 0
    summary_cap: int = 0
    orch_filter: dict | None = None

    def render_kwargs(self):
        return dict(section_filter=self.sections, clean_content=self.clean_content,
                    output_cap=self.output_cap, user_cap=self.user_cap,
                    agent_cap=self.agent_cap, reasoning_cap=self.reasoning_cap,
                    summary_cap=self.summary_cap, orch_filter=self.orch_filter)


class Entry:
    def __init__(self, sid, workspace='/work', title='Sample title'):
        self.session_id = sid
        self.workspace_dir = workspace
        self.title = title
        self.display_title = title
        self.date_created = 1_760_000_000_000
        self.session_file = Path('/fake/session.json')
        self.hidden = False


class Parser:
    def __init__(self, entry):
        self.entry = entry
        self.session_id = entry.session_id
        self.title = entry.title
        self.workspace_dir = entry.workspace_dir
        self.date_created = entry.date_created
        self.kwargs = None

    def to_json(self, **kwargs):
        self.kwargs = kwargs
        return json.dumps({'id': self.session_id, 'kwargs': kwargs})

    def to_markdown(self, **kwargs):
        self.kwargs = kwargs
        return f"markdown {self.session_id}"


class FakeRuntime:
    KIRO_HOME = Path('/fake/kiro')
    @staticmethod
    def ExecutionIndex(home): return object()
    SessionParser = Parser
    CliSessionParser = Parser

    def __init__(self, root):
        self.ide = [Entry('ide-abcdef01'), Entry('ide-bcdef012')]
        self.cli = [Entry('cli-abcdef01')]
        self.output = Path(root)
        self.preferences = {}
        self.default_option_calls = 0
        self.writes = []
        self.parsers = []
        self.last_combined = None
        self.ALL_SECTION_KEYS = {'user_message', 'agent_message'}
        self.EXEC_INDEX = None

    def get_default_export_options(self):
        self.default_option_calls += 1
        return Options({key: True for key in self.ALL_SECTION_KEYS})

    def load_preferences(self):
        return self.preferences

    def save_preferences(self, value):
        self.preferences = value

    def scan_all_sessions(self):
        return self.ide

    def scan_cli_sessions(self):
        return self.cli

    def clean_filename(self, value):
        return value.replace('../', '').replace('..', '').replace('/', '').replace('\\', '')

    def _norm_ws_path(self, path):
        return (path or '').replace('\\', '/').rstrip('/').lower()

    def _parse_sessions_parallel(self, entries, parser_cls=Parser):
        self.parsers = [parser_cls(entry) for entry in entries]
        return self.parsers

    def _full_scope(self): return {'kind': 'full'}
    def _last_scope(self, n): return {'kind': 'last', 'n': n}
    def _first_scope(self, n): return {'kind': 'first', 'n': n}
    def _range_scope(self, start, end): return {'kind': 'range', 'start': start, 'end': end}
    def _live_scope(self): return {'kind': 'live'}

    def apply_extraction_scope(self, parser, scope):
        parser.scope = scope

    def write_export_file(self, path, content):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        candidate = path
        suffix = 2
        while candidate.exists():
            candidate = path.with_name(f'{path.stem}_{suffix}{path.suffix}')
            suffix += 1
        candidate.write_text(content, encoding='utf-8')
        self.writes.append(candidate)
        return candidate

    def combine_parsers_to_json(self, parsers, *args):
        self.last_combined = (parsers, args)
        return json.dumps({'ids': [p.session_id for p in parsers]}), 'combined.json'

    def combine_parsers_to_markdown(self, parsers, *args):
        self.last_combined = (parsers, args)
        return 'combined markdown', 'combined.md'


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rt = FakeRuntime(self.temp.name)

    def invoke(self, argv):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = run_cli(self.rt, argv)
        return code, output.getvalue()

    def test_no_args_returns_control_to_interactive_entry(self):
        self.assertIsNone(run_cli(self.rt, []))

    def test_help_prints_and_returns_zero(self):
        code, output = self.invoke(['--help'])
        self.assertEqual(0, code)
        self.assertIn('export', output)
        self.assertIn('list', output)

    def test_json_list_can_filter_source_and_workspace(self):
        self.rt.ide[0].workspace_dir = '/work/project'
        self.rt.cli[0].workspace_dir = '/elsewhere'
        code, output = self.invoke(['list', '--source', 'ide', '--workspace', '/work/project', '--json'])
        self.assertEqual(0, code)
        self.assertEqual(['ide-abcdef01'], [x['session_id'] for x in json.loads(output)])

    def test_list_all_includes_cli_and_ide(self):
        code, output = self.invoke(['list', '--source', 'all', '--json'])
        self.assertEqual(0, code)
        self.assertEqual({'ide-abcdef01', 'ide-bcdef012', 'cli-abcdef01'},
                         {x['session_id'] for x in json.loads(output)})

    def test_export_chooses_parser_per_source_and_passes_options(self):
        code, _ = self.invoke(['export', '--source', 'cli', '--session', 'cli-abcdef',
                              '--format', 'json', '--output', self.temp.name,
                              '--output-cap', '123', '--clean-chat'])
        self.assertEqual(0, code)
        self.assertEqual(['cli-abcdef01'], [p.session_id for p in self.rt.parsers])
        self.assertEqual(123, self.rt.parsers[0].kwargs['output_cap'])
        self.assertTrue(self.rt.parsers[0].kwargs['clean_content'])
        self.assertEqual(1, len(self.rt.writes))

    def test_export_applies_requested_scope(self):
        code, _ = self.invoke(['export', '--session', 'ide-abcdef', '--last', '3',
                              '--output', self.temp.name])
        self.assertEqual(0, code)
        self.assertEqual({'kind': 'last', 'n': 3}, self.rt.parsers[0].scope)

    def test_unknown_and_ambiguous_ids_fail_without_partial_output(self):
        code, _ = self.invoke(['export', '--session', 'absent', '--output', self.temp.name])
        self.assertEqual(2, code)
        self.assertEqual([], self.rt.writes)
        code, _ = self.invoke(['export', '--session', 'ide-', '--output', self.temp.name])
        self.assertEqual(2, code)
        self.assertEqual([], self.rt.writes)

    def test_existing_export_is_not_overwritten(self):
        existing = Path(self.temp.name) / 'ide-abcdef01.json'
        existing.write_text('keep me', encoding='utf-8')
        code, _ = self.invoke(['export', '--session', 'ide-abcdef01', '--format', 'json',
                              '--output', self.temp.name])
        self.assertEqual(0, code)
        self.assertEqual('keep me', existing.read_text(encoding='utf-8'))
        self.assertEqual(2, len(list(Path(self.temp.name).glob('*.json'))))

    def test_any_bad_id_prevents_all_files_from_being_written(self):
        code, _ = self.invoke(['export', '--session', 'ide-abcdef01', '--session', 'missing',
                              '--output', self.temp.name])
        self.assertEqual(2, code)
        self.assertEqual([], self.rt.writes)

    def test_reuse_applies_saved_scope_format_and_source(self):
        self.rt.preferences = {'source': 'cli', 'format': 'json',
                               'scope': {'mode': 'last', 'n': 4, 'label': 'last 4 turns'},
                               'export_options': {'output_cap': 77}}
        code, _ = self.invoke(['export', '--session', 'cli-abcdef01', '--reuse',
                              '--output', self.temp.name])
        self.assertEqual(0, code)
        self.assertEqual({'mode': 'last', 'n': 4, 'label': 'last 4 turns'},
                         self.rt.parsers[0].scope)
        self.assertEqual(77, self.rt.parsers[0].kwargs['output_cap'])
        self.assertEqual(1, self.rt.default_option_calls)
        self.assertEqual(1, len(list(Path(self.temp.name).glob('*.json'))))

    def test_explicit_scope_overrides_reused_scope(self):
        self.rt.preferences = {'scope': {'mode': 'last', 'n': 4, 'label': 'last 4 turns'}}
        code, _ = self.invoke(['export', '--session', 'ide-abcdef01', '--reuse', '--first', '2',
                              '--output', self.temp.name])
        self.assertEqual(0, code)
        self.assertEqual({'kind': 'first', 'n': 2}, self.rt.parsers[0].scope)

    def test_modern_ide_does_not_build_legacy_execution_index(self):
        self.rt.index_builds = 0
        class Index:
            def __init__(self, home): pass
            def build(self): self_outer.index_builds += 1
        self_outer = self.rt
        self.rt.ExecutionIndex = Index
        code, _ = self.invoke(['export', '--session', 'ide-abcdef01', '--output', self.temp.name])
        self.assertEqual(0, code)
        self.assertEqual(0, self.rt.index_builds)

    def test_parser_failure_or_partial_result_does_not_report_success_or_write(self):
        for result in ([], [Parser(self.rt.ide[0])]):
            with self.subTest(result_count=len(result)):
                self.rt._parse_sessions_parallel = lambda entries, parser_cls=Parser, result=result: result
                code, _ = self.invoke(['export', '--session', 'ide-abcdef01',
                                      '--session', 'ide-bcdef012', '--output', self.temp.name])
                self.assertEqual(1, code)
                self.assertEqual([], self.rt.writes)

    def test_untrusted_session_id_cannot_escape_output_directory(self):
        self.rt.ide[0].session_id = '../outside'
        destination = Path(self.temp.name) / 'exports'
        code, _ = self.invoke(['export', '--session', '../outside', '--output', str(destination)])
        self.assertEqual(0, code)
        self.assertEqual(1, len(self.rt.writes))
        self.assertEqual(destination.resolve(), self.rt.writes[0].parent.resolve())
        self.assertEqual('outside.md', self.rt.writes[0].name)

    def test_missing_default_options_helper_has_a_safe_fallback(self):
        self.rt.get_default_export_options = None
        code, _ = self.invoke(['export', '--session', 'ide-abcdef01', '--output', self.temp.name])
        self.assertEqual(0, code)
        self.assertEqual(1, len(self.rt.writes))

    def test_nonexistent_output_directory_is_created(self):
        destination = Path(self.temp.name) / 'new' / 'nested'
        code, _ = self.invoke(['export', '--session', 'ide-abcdef01', '--output', str(destination)])
        self.assertEqual(0, code)
        self.assertTrue(destination.is_dir())

    def test_invalid_scope_and_output_cap_return_two(self):
        for extra in (['--last', '0'], ['--turns', '0:1'], ['--output-cap', '-1']):
            with self.subTest(extra=extra):
                code, _ = self.invoke(['export', '--session', 'ide-abcdef01', *extra,
                                      '--output', self.temp.name])
                self.assertEqual(2, code)
                self.assertEqual([], self.rt.writes)

    def test_invalid_arguments_return_two_instead_of_entering_interactive_mode(self):
        code, output = self.invoke(['export', '--last', '3', '--first', '2'])
        self.assertEqual(2, code)
        self.assertIn('error', output.lower())


if __name__ == '__main__':
    unittest.main()
