"""Synthetic behavior tests for the reusable export renderers."""
import json
from pathlib import Path
import unittest

from kiro_export.options import ExportOptions
from kiro_export.exporting import (
    RenderContext, _auxiliary_export_counts, _json_export_info, _json_value,
    _nested_events, _session_read_error_count, cap_text, render_markdown,
    select_items, serialize_sessions_json,
)

class FakeParser:
    def __init__(self, events=None):
        self.data = events or []
        self.title = 'Synthetic fixture'
        self.session_id = 'synthetic-id'
        self.workspace_dir = '/example/project'
        self.date_created = 0
        self.metadata = {'source': 'Kiro IDE'}
        self.model_titles = set()
        self.autonomy_mode = None
        self.session_type = None
        self.execution_count = 0
        self.user_turn_count = 2
        self.context_usage_pct = 0.0
        self.credits_used = 0.0
        self.parent_session_ids = []
        self.continuation_count = 0
        self.compaction_count = 0
        self.started_from_compaction = False
        self.hidden = False
        self.source_turn_count = 2
        self.source_event_count = len(self.data)
        self.extraction_scope = {'mode': 'full'}

    def get_turn_count(self):
        return self.user_turn_count

    def to_markdown(self, **kwargs):
        return f'nested-render:{self.title}:{len(self.data)}'


def context_for(calls=None):
    calls = calls if calls is not None else []

    def guess_lang(path):
        calls.append(('guess_lang', path))
        return 'python' if path.endswith('.py') else 'text'

    def strip_ide_context(content):
        calls.append(('strip_ide_context', content))
        return content.replace('[context]', '').strip()

    def load_heavy(item, filt, output_cap):
        calls.append(('load_heavy', item, filt, output_cap))
        return {}

    def render_orch(item, filt, output_cap, heavy):
        calls.append(('render_orch', item, filt, output_cap, heavy))
        return '**Synthetic orchestration**'

    def json_orch(item, filt, output_cap):
        calls.append(('json_orch', item, filt, output_cap))
        return {'type': 'orchestration', 'crew_status': item.get('crew_status'), 'stages': []}

    return RenderContext(guess_lang, strip_ide_context, load_heavy,
                         render_orch, json_orch)


class ExportingTests(unittest.TestCase):
    def test_markdown_uses_options_and_context_without_mutating_parser(self):
        parser = FakeParser([
            {'type': 'user_message', 'content': '[context] duplicate'},
            {'type': 'user_message', 'content': '[context] duplicate'},
            {'type': 'agent_message', 'content': 'answer'},
            {'type': 'file_create', 'path': 'hello.py', 'modified_content': 'print(1)'},
            {'type': 'orchestration', 'crew_status': 'completed'},
            {'type': 'sub_agent', 'kind': 'invoke', 'sub_execution': {
                'id': 'child-1', 'events': [{'type': 'agent_message', 'content': 'nested'}],
            }},
        ])
        original = list(parser.data)
        calls = []
        options = ExportOptions(
            sections={'user_message': True, 'agent_message': True,
                      'file_create': True, 'orchestration': True, 'sub_agent': True},
            clean_content=True, user_cap=1, orch_filter={'layers': {'reasoning': True}},
        )
        output = render_markdown(parser, options, context_for(calls))
        self.assertIn('# Synthetic fixture', output)
        self.assertIn('## 👤 User\n\nduplicate', output)
        self.assertEqual(1, output.count('## 👤 User'))
        self.assertIn('```python\nprint(1)\n```', output)
        self.assertIn('**Synthetic orchestration**', output)
        self.assertIn('nested-render:Sub-execution child-1:1', output)
        self.assertEqual(original, parser.data)
        self.assertTrue(any(call[0] == 'strip_ide_context' for call in calls))
        self.assertTrue(any(call[0] == 'guess_lang' for call in calls))
        self.assertTrue(any(call[0] == 'load_heavy' for call in calls))

    def test_json_selection_caps_sections_helpers_and_document_shape(self):
        child_events = [{'type': 'error', 'kind': 'session_read', 'message': 'fixture'}]
        parser = FakeParser([
            {'type': 'user_message', 'content': '[context] first'},
            {'type': 'user_message', 'content': '[context] last'},
            {'type': 'terminal_output', 'output': 'one\ntwo\nthree'},
            {'type': 'orchestration', 'crew_status': 'completed'},
            {'type': 'sub_agent', 'kind': 'invoke', 'sub_execution': {
                'id': 'child-1', 'status': 'loaded', 'events': child_events,
            }},
            {'type': 'web_fetch', 'url': 'https://example.test', 'content': 'one\ntwo\nthree'},
            {'type': 'error', 'kind': 'session_read', 'message': 'fixture'},
        ])
        parser.source_event_count = len(parser.data)
        options = ExportOptions(
            sections={'user_message': True, 'terminal_output': True,
                      'orchestration': True, 'sub_agent': True, 'web_fetch': True,
                      'session_meta': False},
            clean_content=True, output_cap=2, user_cap=1,
            orch_filter={'statuses': {'completed': True}, 'layers': {}},
        )
        calls = []
        doc = json.loads(serialize_sessions_json([parser], options, context_for(calls)))
        self.assertEqual('kiro-session-export', doc['format'])
        self.assertEqual(1, doc['schema_version'])
        self.assertEqual({'user_message': True, 'terminal_output': True,
                          'orchestration': True, 'sub_agent': True,
                          'web_fetch': True, 'session_meta': False}, doc['options']['sections'])
        events = doc['sessions'][0]['events']
        users = [event for event in events if event['type'] == 'user_message']
        self.assertEqual(['last'], [event['content'] for event in users])
        terminal = next(event for event in events if event['type'] == 'terminal_output')
        self.assertEqual('... (1 lines trimmed) ...\ntwo\nthree', terminal['output'])
        self.assertEqual('orchestration',
                         next(event['type'] for event in events if event['type'] == 'orchestration'))
        self.assertEqual(2, doc['sessions'][0]['export_info']['read_error_count'])
        self.assertTrue(any(call[0] == 'json_orch' for call in calls))
        self.assertTrue(any(call[0] == 'strip_ide_context' for call in calls))
        self.assertNotIn('id', doc['sessions'][0])

    def test_explicit_empty_orchestration_filter_is_preserved(self):
        parser = FakeParser([{'type': 'orchestration', 'crew_status': 'completed'}])
        options = ExportOptions(sections={'orchestration': True}, orch_filter={})
        calls = []
        context = context_for(calls)
        document = json.loads(serialize_sessions_json([parser], options, context))
        self.assertEqual({}, document['options']['orchestration'])
        self.assertEqual({}, next(call[2] for call in calls if call[0] == 'json_orch'))

        calls.clear()
        render_markdown(parser, options, context)
        render_call = next(call for call in calls if call[0] == 'render_orch')
        self.assertEqual({}, render_call[2])
        self.assertFalse(any(call[0] == 'load_heavy' for call in calls))

    def test_shared_helpers_keep_json_safe_counts_and_last_line_cap(self):
        value = {'path': Path('relative/file.txt'), 'values': (1, {3, 2})}
        self.assertEqual({'path': str(Path('relative/file.txt')), 'values': [1, [2, 3]]},
                         _json_value(value))
        nested = [{'type': 'sub_agent', 'sub_execution': {
            'id': 'child', 'status': 'loaded', 'events': [
                {'type': 'error', 'kind': 'session_read'},
                {'type': 'terminal_output', 'external_outputs': [
                    {'status': 'loaded', 'file': 'a'}, {'status': 'failed', 'file': 'b'},
                ]},
            ],
        }}]
        flattened = list(_nested_events(nested))
        self.assertEqual(3, len(flattened))
        self.assertEqual(1, _session_read_error_count(nested))
        self.assertEqual({'sub_execution_count': 1,
                          'external_output_files': {'loaded': 1, 'failed': 1}},
                         _auxiliary_export_counts(nested))
        self.assertEqual('... (1 lines trimmed) ...\nlast\nend', cap_text('first\nlast\nend', 2))
        parser = FakeParser(nested)
        info = _json_export_info(parser, {'sub_agent': True}, nested)
        self.assertEqual({'mode': 'full'}, info['scope'])
        self.assertEqual(1, info['sub_execution_count'])

    def test_export_info_without_explicit_scope_keeps_full_scope_label(self):
        parser = FakeParser([])
        del parser.extraction_scope
        self.assertEqual({'mode': 'full', 'label': 'full session'},
                         _json_export_info(parser, {}, [])['scope'])

    def test_select_items_shares_section_and_tail_cap_selection(self):
        data = [{'type': 'user_message', 'content': str(i)} for i in range(4)]
        data += [{'type': 'reasoning', 'content': 'private'}]
        options = ExportOptions(sections={'user_message': True}, user_cap=2)
        self.assertEqual(['2', '3'], [item['content'] for item in select_items(data, options)])

    def test_markdown_matches_baseline_layout_for_complex_synthetic_events(self):
        parser = FakeParser([
            {'type': 'file_read', 'files': [{'path': 'src/app.py', 'start': 2, 'end': 4}],
             'tool': 'readFile', 'output': 'line one\nline two'},
            {'type': 'terminal_output', 'result_only': True, 'tool': 'runCommand',
             'state': 'Failed', 'output': 'failure detail\ntrace tail'},
            {'type': 'summarization', 'content': 'Earlier setup retained.', 'where': 'intro'},
            {'type': 'sub_agent', 'kind': 'invoke', 'name': 'reviewer',
             'explanation': 'Check the change.', 'prompt': 'Inspect src/app.py.'},
        ])
        sections = {'file_read': True, 'terminal_output': True,
                    'summarization': True, 'sub_agent': True}
        options = ExportOptions(sections=sections, output_cap=1)
        expected = (
            '# Synthetic fixture\n\n'
            '### 📖 Read (readFile)\n\n'
            '- `src/app.py  [2–4]`\n\n'
            '```text\n... (1 lines trimmed) ...\nline two\n```\n\n'
            '**Result — `runCommand` (failed):**\n\n'
            '```text\n... (1 lines trimmed) ...\ntrace tail\n```\n\n'
            '## ✂️ Compaction Summary (intro)\n\n'
            'Earlier setup retained.\n\n'
            '### 🧩 Sub-Agent → `reviewer`\n\n'
            '> Check the change.\n\n'
            '```text\nInspect src/app.py.\n```\n'
        )
        self.assertEqual(expected, render_markdown(parser, options, context_for()))


if __name__ == '__main__':
    unittest.main()
