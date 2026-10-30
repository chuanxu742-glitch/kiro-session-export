"""Synthetic tests for export options and user preferences."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kiro_export.options import ExportOptions
from kiro_export import preferences


class ExportOptionsTests(unittest.TestCase):
    def test_legacy_round_trip_and_render_kwargs(self):
        legacy = ({'user_message': True}, True, 12, 3, 4, 5, 6,
                  {'layers': {'plan': True}})
        options = ExportOptions.from_legacy(legacy)
        self.assertEqual(legacy, options.legacy_tuple())
        self.assertEqual(legacy, tuple(options))
        self.assertEqual(legacy[2], options[2])
        self.assertEqual({
            'section_filter': legacy[0], 'clean_content': True,
            'output_cap': 12, 'user_cap': 3, 'agent_cap': 4,
            'reasoning_cap': 5, 'summary_cap': 6, 'orch_filter': legacy[7],
        }, options.render_kwargs())

    def test_copy_boundaries_and_dict_round_trip(self):
        sections = {'user_message': True}
        orch = {'layers': {'plan': True}}
        options = ExportOptions(sections=sections, orch_filter=orch)
        sections['agent_message'] = True
        orch['layers']['plan'] = False
        self.assertEqual({'user_message': True}, options.sections)
        self.assertTrue(options.orch_filter['layers']['plan'])
        serialized = options.as_dict()
        serialized['sections']['user_message'] = False
        serialized['orch_filter']['layers']['plan'] = False
        self.assertTrue(options.sections['user_message'])
        self.assertTrue(options.orch_filter['layers']['plan'])
        rebuilt = ExportOptions.from_dict(options.as_dict())
        self.assertEqual(options.legacy_tuple(), rebuilt.legacy_tuple())

    def test_legacy_input_shape_is_checked(self):
        with self.assertRaises((TypeError, ValueError)):
            ExportOptions.from_legacy(({}, False))


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'nested' / 'settings.json'
        self.env = patch.dict(os.environ, {'KIRO_EXPORT_CONFIG': str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_path_is_resolved_from_environment_on_each_call(self):
        self.assertEqual(self.path, preferences.preferences_path())
        alternate = self.path.with_name('other.json')
        with patch.dict(os.environ, {'KIRO_EXPORT_CONFIG': str(alternate)}):
            self.assertEqual(alternate, preferences.preferences_path())

    def test_defaults_and_save_load_whitelisted_settings(self):
        defaults = preferences.load_preferences()
        self.assertEqual(0, defaults['export_options']['output_cap'])
        self.assertEqual('ide', defaults['source'])
        values = {
            'source': 'cli', 'format': 'json', 'destination': 'f',
            'output_location': 'project', 'file_mode': 'combined',
            'scope': {'mode': 'range', 'start': 2, 'end': 8},
            'export_options': ExportOptions(sections={'reasoning': False}).as_dict(),
            'unknown': 'discard me', 'session_id': 'never persist',
            'chat_body': 'private text',
        }
        self.assertTrue(preferences.save_preferences(values))
        self.assertEqual(values['scope'], preferences.load_preferences()['scope'])
        raw = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertNotIn('unknown', raw)
        self.assertNotIn('session_id', raw)
        self.assertNotIn('chat_body', raw)

    def test_invalid_values_fall_back_and_corrupt_json_does_not_raise(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            'source': 'invalid', 'format': 3, 'destination': 'x',
            'output_location': False, 'file_mode': [],
            'scope': {'mode': [], 'start': -1, 'end': 'bad'},
            'export_options': {'sections': {'x': 1}, 'output_cap': -4,
                               'clean_content': 'yes'},
            'session_id': 'discard',
        }), encoding='utf-8')
        loaded = preferences.load_preferences()
        self.assertEqual('ide', loaded['source'])
        self.assertEqual('markdown', loaded['format'])
        self.assertEqual(0, loaded['export_options']['output_cap'])
        self.assertEqual({'mode': 'full'}, loaded['scope'])
        self.path.write_text(json.dumps({
            'scope': {'mode': 'first', 'n': 0},
            'export_options': {'sections': {'user_message': True, 'unknown': True},
                               'orch_filter': {'statuses': {'error': True, 'body': 'private'},
                                               'layers': {'reasoning': False, 'chat': 'private'},
                                               'latest_only': True, 'body': 'private'}},
        }), encoding='utf-8')
        loaded = preferences.load_preferences()
        self.assertEqual({'mode': 'full'}, loaded['scope'])
        self.assertNotIn('unknown', loaded['export_options']['sections'])
        self.assertEqual({'statuses': {'error': True}, 'layers': {'reasoning': False},
                          'latest_only': True}, loaded['export_options']['orch_filter'])
        self.path.write_text('{broken', encoding='utf-8')
        self.assertEqual(0, preferences.load_preferences()['export_options']['output_cap'])

    def test_partial_save_preserves_other_valid_settings_and_failure_is_false(self):
        self.assertTrue(preferences.save_preferences({'source': 'cli', 'format': 'json'}))
        self.assertTrue(preferences.save_preferences({'destination': 'c'}))
        self.assertTrue(preferences.save_preferences({
            'export_options': {'sections': {'reasoning': False}, 'output_cap': 9},
        }))
        self.assertTrue(preferences.save_preferences({
            'export_options': {'clean_content': True},
        }))
        loaded = preferences.load_preferences()
        self.assertEqual('cli', loaded['source'])
        self.assertEqual('json', loaded['format'])
        self.assertEqual('c', loaded['destination'])
        self.assertEqual(9, loaded['export_options']['output_cap'])
        self.assertFalse(loaded['export_options']['sections']['reasoning'])
        self.assertTrue(loaded['export_options']['clean_content'])
        with patch.object(preferences, 'preferences_path', side_effect=OSError('blocked')):
            self.assertFalse(preferences.save_preferences({'source': 'ide'}))


if __name__ == '__main__':
    unittest.main()
