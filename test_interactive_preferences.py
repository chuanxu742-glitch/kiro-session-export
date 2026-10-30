"""Interactive preference integration uses synthetic sessions and a temporary config."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

import test_session_formats as fixtures


class InteractivePreferencesTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SessionFormatTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.kiro = fixtures.kiro

    def test_saved_filter_options_are_restored_without_mutating_preferences(self):
        k = self.kiro
        k.save_preferences({'export_options': {'sections': {'reasoning': False}, 'output_cap': 77}})
        before = k.load_preferences()
        parser = self.fixture.parse_modern()
        with patch.object(k, 'read_key', return_value='Q'), contextlib.redirect_stdout(io.StringIO()):
            options = k.ExportOptions.from_legacy(k.interactive_filter([parser]))
        self.assertFalse(options.sections['reasoning'])
        self.assertEqual(77, options.output_cap)
        self.assertEqual(before, k.load_preferences())

    def test_saved_format_is_enter_default(self):
        k = self.kiro
        k.save_preferences({'format': 'json'})
        with patch('builtins.input', return_value=''), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual('json', k.select_export_format())

    def test_source_menu_reuses_settings_only_when_explicitly_selected(self):
        k = self.kiro
        k.save_preferences({'source': 'ide', 'format': 'json'})
        with patch('builtins.input', side_effect=['r']), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual('ide', k.select_session_source())
        self.assertTrue(k._REUSE_EXPORT_SETTINGS)
        with patch('builtins.input', return_value='1'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual('ide', k.select_session_source())
        self.assertFalse(k._REUSE_EXPORT_SETTINGS)

    def test_reuse_exports_saved_scope_without_export_wizard(self):
        k = self.kiro
        self.fixture.modern_session(payloads=[
            {'type': 'user', 'content': 'First'}, {'type': 'assistant', 'content': 'First answer'},
            {'type': 'user', 'content': 'Second'}, {'type': 'assistant', 'content': 'Second answer'},
        ])
        destination = self.fixture.root / 'reuse'
        destination.mkdir()
        k.save_preferences({'format': 'json', 'destination': 'f', 'scope': {'mode': 'last', 'n': 1}})
        with patch.object(k, '_REUSE_EXPORT_SETTINGS', True), \
                patch.object(k, '_saved_output_location', return_value=('single', destination)), \
                patch.object(k, 'interactive_filter') as filter_ui, \
                patch.object(k, 'select_extraction_scope') as scope_ui, \
                patch.object(k, 'select_export_format') as format_ui, \
                patch.object(k, 'maybe_open_directory'), patch('builtins.input', return_value=''), \
                contextlib.redirect_stdout(io.StringIO()):
            k.process_conversion('1', k.scan_all_sessions(), build_execution_index=False)
        filter_ui.assert_not_called()
        scope_ui.assert_not_called()
        format_ui.assert_not_called()
        document = json.loads(next(destination.glob('*.json')).read_text(encoding='utf-8'))
        session = document['sessions'][0]
        self.assertEqual(['Second'], [event['content'] for event in session['events'] if event['type'] == 'user_message'])
        self.assertEqual('last', session['export_info']['scope']['mode'])

    def test_successful_export_remembers_choices(self):
        k = self.kiro
        self.fixture.modern_session()
        self.fixture.run_json_pipeline(k.scan_all_sessions(), ['j', 'f', ''])
        saved = k.load_preferences()
        self.assertEqual('json', saved['format'])
        self.assertEqual('f', saved['destination'])
        self.assertEqual('ide', saved['source'])
        self.assertEqual(0, saved['export_options']['output_cap'])

    def test_saved_scope_rebuilds_a_descriptive_selection(self):
        k = self.kiro
        self.assertEqual(k._range_scope(2, 4), k._saved_scope({'scope': {'mode': 'range', 'start': 2, 'end': 4}}))

    def test_saved_script_directory_is_enter_default(self):
        k = self.kiro
        project = self.fixture.root / 'workspace'
        project.mkdir()
        k.save_preferences({'output_location': 'script'})
        with patch.object(k, '_project_dirs_from_parsers', return_value=[project]), \
                patch('builtins.input', return_value=''), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(('single', k.script_output_directory()), k.choose_output_location([], 'separate'))


if __name__ == '__main__':
    unittest.main()
