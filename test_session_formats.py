"""Synthetic fixtures only: never copy local conversation content into tests."""
import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('kiro_md', Path(__file__).with_name('kiro-md.py'))
kiro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kiro)


class SessionFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'KIRO_EXPORT_CONFIG': str(self.root / 'preferences.json')})
        env.start()
        self.addCleanup(env.stop)
        self.legacy = self.root / 'legacy' / 'workspace-sessions'
        self.modern = self.root / 'sessions'
        self.cli = self.root / 'cli'
        for name, value in [('WORKSPACE_SESSIONS_DIR', self.legacy),
                            ('KIRO_HOME', self.legacy.parent),
                            ('KIRO_IDE_SESSIONS_DIR', self.modern),
                            ('KIRO_CLI_SESSIONS_DIR', self.cli),
                            ('EXEC_INDEX', None), ('CHAIN_GRAPH', None), ('_REUSE_EXPORT_SETTINGS', False)]:
            p = patch.object(kiro, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path

    def legacy_session(self, sid='old-session'):
        ws = base64.urlsafe_b64encode(b'/example/project').decode().rstrip('=')
        directory = self.legacy / ws
        self.write_json(directory / 'sessions.json', [{
            'sessionId': sid, 'title': 'Legacy conversation', 'dateCreated': 1000,
            'workspaceDirectory': '/example/project',
        }])
        self.write_json(directory / (sid + '.json'), {
            'sessionId': sid, 'history': [
                {'message': {'role': 'user', 'content': 'Legacy question'}},
                {'message': {'role': 'assistant', 'content': 'Legacy answer'}},
            ],
        })

    def modern_session(self, sid='sess-new-session', payloads=None, **metadata):
        path = self.modern / 'workspace-hash' / sid / 'session.json'
        data = {'schemaVersion': '1.0.0', 'dataModelVersion': 3, 'id': sid,
                'title': '新版对话', 'workspacePaths': ['/example/project'],
                'rootPaths': ['/example/project'], 'createdAt': '2026-10-28T10:00:00Z',
                'lastModifiedAt': '2026-10-29T10:00:00Z', 'modelId': 'example-model',
                'agentMode': 'vibe', 'autopilot': True}
        data.update(metadata)
        self.write_json(path, data)
        if payloads is None:
            payloads = [{'type': 'user', 'content': '你好，新版 Kiro'},
                        {'type': 'assistant', 'operationType': 'Say', 'content': '你好，已读取对话'}]
        stream = path.with_name('messages.jsonl')
        stream.write_text(''.join(json.dumps({
            'id': 'message-' + str(i), 'timestamp': '2026-10-28T10:00:00Z', 'payload': p,
        }, ensure_ascii=False) + '\n' for i, p in enumerate(payloads)), encoding='utf-8')
        return path

    def parse_modern(self, payloads=None, **metadata):
        self.modern_session(payloads=payloads, **metadata)
        entries = kiro.scan_all_sessions()
        self.assertEqual(1, len(entries), 'The new IDE layout must be discovered')
        return kiro.SessionParser(entries[0])

    def test_legacy_ide_scan_and_export(self):
        self.legacy_session()
        entries = kiro.scan_all_sessions()
        self.assertEqual(['old-session'], [e.session_id for e in entries])
        parser = kiro.SessionParser(entries[0])
        md = parser.to_markdown()
        self.assertIn('Legacy question', md)
        self.assertIn('Legacy answer', md)
        self.assertEqual(1, parser.get_turn_count())

    def test_legacy_cli_scan_and_export(self):
        self.write_json(self.cli / 'cli-session.json', {
            'session_id': 'cli-session', 'title': 'CLI question', 'cwd': '/example/project',
            'created_at': '2026-10-28T10:00:00Z',
            'session_state': {'conversation_metadata': {'user_turn_metadatas': [{
                'result': {'Ok': {'role': 'assistant', 'content': [
                    {'kind': 'text', 'data': 'CLI answer'},
                ]}},
            }]}},
        })
        entries = kiro.scan_cli_sessions()
        self.assertEqual(['cli-session'], [e.session_id for e in entries])
        md = kiro.CliSessionParser(entries[0]).to_markdown()
        self.assertIn('CLI question', md)
        self.assertIn('CLI answer', md)

    def test_modern_scan_preview_size_and_id_lookup(self):
        path = self.modern_session()
        entries = kiro.scan_all_sessions()
        self.assertEqual(['sess-new-session'], [e.session_id for e in entries])
        entry = entries[0]
        self.assertEqual('/example/project', entry.workspace_dir)
        self.assertEqual('新版对话', entry.display_title)
        self.assertEqual(1793181600000, entry.date_created)
        self.assertEqual(path.stat().st_size + path.with_name('messages.jsonl').stat().st_size, entry.size)
        entry.load_preview()
        self.assertIn('你好', entry.preview_text)
        self.assertEqual([entry], kiro._find_entries_by_session_id(entries, 'sess-new'))

    def test_modern_and_legacy_coexist_and_migrated_duplicate_prefers_modern(self):
        self.legacy_session('sess-migrated')
        self.modern_session('sess-migrated')
        self.modern_session('sess-another', createdAt='2026-10-29T10:00:00Z')
        entries = kiro.scan_all_sessions()
        self.assertEqual(['sess-another', 'sess-migrated'], [e.session_id for e in entries])
        self.assertEqual('session.json', entries[1].session_file.name)

    def test_modern_scan_skips_invalid_metadata(self):
        self.modern_session()
        self.write_json(self.modern / 'hash' / 'invalid' / 'session.json', [])
        self.write_json(self.modern / 'hash' / 'unrelated' / 'session.json', {'title': 'not a session'})
        self.assertEqual(1, len(kiro.scan_all_sessions()))

    def test_modern_messages_reasoning_summary_and_scope(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': 'First question'},
            {'type': 'turn_start', 'executionId': 'exec-1'},
            {'type': 'assistant', 'operationType': 'Reasoning', 'content': 'Private reasoning'},
            {'type': 'assistant', 'operationType': 'Say', 'content': 'First answer'},
            {'type': 'assistant', 'operationType': 'Summary', 'content': 'Earlier context summary'},
            {'type': 'tombstone', 'kind': 'summarization', 'effectiveFromMessageId': 'message-4'},
            {'type': 'user', 'content': 'Second question'},
            {'type': 'assistant', 'operationType': 'Say', 'content': 'Second answer'},
        ])
        md = parser.to_markdown()
        for text in ('First question', 'First answer', 'Private reasoning', 'Earlier context summary', 'Second answer'):
            self.assertIn(text, md)
        self.assertEqual(2, parser.get_turn_count())
        self.assertEqual(1, parser.execution_count)
        self.assertEqual(1, parser.compaction_count)
        filtered = parser.to_markdown(section_filter={'user_message': True, 'agent_message': True})
        self.assertNotIn('Private reasoning', filtered)
        parser.trim_to_live_context()
        live = parser.to_markdown()
        self.assertNotIn('First question', live)
        self.assertIn('Earlier context summary', live)
        self.assertIn('Second answer', live)

    def test_modern_command_result_and_unknown_tool_keep_order(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': 'Run a command'},
            {'type': 'tool_call', 'toolCallId': 'cmd', 'toolName': 'execute_pwsh',
             'actionType': 'run_command', 'args': {'command': 'Write-Output hello', 'cwd': '/example/project'}},
            {'type': 'assistant', 'operationType': 'Say', 'content': 'Command is running'},
            {'type': 'tool_result', 'toolCallId': 'cmd', 'content': 'hello', 'success': True},
            {'type': 'tool_call', 'toolCallId': 'unknown', 'toolName': 'future_tool',
             'args': {'example': 'kept-argument'}},
            {'type': 'tool_result', 'toolCallId': 'unknown', 'content': 'kept-result', 'success': False},
        ])
        md = parser.to_markdown()
        self.assertLess(md.index('Write-Output hello'), md.index('Command is running'))
        self.assertLess(md.index('Command is running'), md.index('\nhello\n'))
        for text in ('future_tool', 'kept-argument', 'kept-result'):
            self.assertIn(text, md)
        self.assertTrue(any(x.get('state') == 'Failed' for x in parser.data))
        filtered = parser.to_markdown(section_filter={'user_message': True})
        self.assertNotIn('Write-Output hello', filtered)
        self.assertNotIn('kept-result', filtered)

    def test_modern_file_web_process_and_mcp_tools(self):
        cases = [
            ('read_file', 'read_files', {'path': 'main.py', 'offset': 0, 'limit': 5}, 'file_read'),
            ('fs_write', 'fs_write', {'path': 'new.py', 'text': 'print(42)'}, 'file_create'),
            ('str_replace', 'replace', {'path': 'main.py', 'oldStr': 'before', 'newStr': 'after'}, 'file_edit'),
            ('fs_append', 'append', {'path': 'main.py', 'text': 'appended text'}, 'file_edit'),
            ('delete_file', 'delete', {'targetFile': 'old.py'}, 'file_delete'),
            ('grep_search', 'search', {'query': 'needle'}, 'code_search'),
            ('remote_web_search', 'remote_web_search', {'query': 'example query'}, 'web_search'),
            ('web_fetch', 'web_fetch', {'url': 'https://example.com'}, 'web_fetch'),
            ('control_pwsh_process', 'control_process', {'action': 'start', 'command': 'example'}, 'process_ctrl'),
            ('get_process_output', 'get_process_output', {'terminalId': 'terminal-1'}, 'process_ctrl'),
            ('mcp_example', 'mcp', {'serverName': 'example', 'toolName': 'lookup', 'toolArgs': {'q': 1}}, 'mcp_tool'),
        ]
        payloads = [{'type': 'user', 'content': 'Exercise tools'}]
        for i, (name, action, args, section) in enumerate(cases):
            payloads.extend([
                {'type': 'tool_call', 'toolCallId': str(i), 'toolName': name, 'actionType': action, 'args': args},
                {'type': 'tool_result', 'toolCallId': str(i), 'content': 'Result ' + name, 'success': True},
            ])
        parser = self.parse_modern(payloads)
        md = parser.to_markdown()
        for name, action, args, section in cases:
            with self.subTest(tool=name):
                self.assertTrue(any(x['type'] == section and x.get('tool') == name for x in parser.data))
                self.assertIn('Result ' + name, md)
        for text in ('main.py', 'print(42)', 'after', 'appended text', 'example query', 'https://example.com'):
            self.assertIn(text, md)

    def test_modern_metadata_subagents_errors_and_clarification(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': 'Question'},
            {'type': 'session_metadata', 'key': 'contextUsage', 'value': {'usagePercentage': 42.5}},
            {'type': 'usage_summary', 'promptTurnSummaries': [{'unit': 'credit', 'usage': 0.25}]},
            {'type': 'sub_agent_start', 'subSessionId': 'child', 'subAgentName': 'reviewer', 'prompt': 'Review this'},
            {'type': 'sub_agent_complete', 'subSessionId': 'child', 'response': 'Review complete', 'status': 'completed'},
            {'type': 'pending_interaction', 'toolCallId': 'consent', 'question': 'Allow action?',
             'interactionType': 'consent', 'options': []},
            {'type': 'interaction_resolved', 'toolCallId': 'consent', 'selectedOption': 'Allow once'},
            {'type': 'session_metadata', 'key': 'displayError', 'value': {'message': 'Example failure', 'errorType': 'test'}},
        ])
        md = parser.to_markdown()
        for text in ('example-model', '42.5%', '0.2500', 'reviewer', 'Review complete',
                     'Allow action?', 'Allow once', 'Example failure'):
            self.assertIn(text, md)

    def test_modern_images_omit_base64_and_partial_record_warns(self):
        path = self.modern_session(payloads=[
            {'type': 'user', 'content': 'See screenshot',
             'images': [{'data': 'PRIVATE_IMAGE_BYTES', 'mimeType': 'image/png'}]},
            {'type': 'assistant', 'operationType': 'Say', 'content': 'Visible answer'},
        ])
        with path.with_name('messages.jsonl').open('a', encoding='utf-8') as stream:
            stream.write('{"payload":')
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        md = parser.to_markdown()
        self.assertIn('Visible answer', md)
        self.assertIn('[Image', md)
        self.assertNotIn('PRIVATE_IMAGE_BYTES', md)
        self.assertTrue(any(x['type'] == 'error' for x in parser.data))

    def test_modern_missing_stream_reports_error(self):
        path = self.modern_session()
        path.with_name('messages.jsonl').unlink()
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        self.assertTrue(any(x['type'] == 'error' for x in parser.data))

    def test_modern_ide_menu_does_not_require_legacy_directory(self):
        self.modern_session()
        output = io.StringIO()
        with patch('builtins.input', side_effect=['x', 'q']), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as stopped:
                kiro.interactive_loop_ide()
        self.assertEqual(0, stopped.exception.code)
        self.assertIn('新版对话', output.getvalue())
        self.assertNotIn('folder not found', output.getvalue())

    def test_session_id_finder_includes_modern_ide(self):
        self.modern_session()
        output = io.StringIO()
        with patch('builtins.input', side_effect=['sess-new-session', 'n']), contextlib.redirect_stdout(output):
            kiro.interactive_find_session_by_id()
        self.assertIn('SESSION FOUND', output.getvalue())
        self.assertIn('Kiro IDE', output.getvalue())

    def test_conversion_pipeline_writes_modern_markdown(self):
        self.modern_session(payloads=[
            {'type': 'user', 'content': '你好，新版 Kiro\r\n第二行'},
            {'type': 'assistant', 'operationType': 'Say', 'content': '你好，已读取对话'},
        ])
        destination = self.root / 'exports'
        destination.mkdir()
        settings = ({key: True for key in kiro.ALL_SECTION_KEYS}, False, 0, 0, 0, 0, 0,
                    kiro.default_orch_filter())
        output = io.StringIO()
        with patch('builtins.input', side_effect=['m', 'f', '']), \
                patch.object(kiro, 'interactive_filter', return_value=settings), \
                patch.object(kiro, 'choose_output_location', return_value=('single', destination)), \
                patch.object(kiro, 'maybe_open_directory'), contextlib.redirect_stdout(output):
            kiro.process_conversion('1', kiro.scan_all_sessions(), allow_scope=False)
        files = list(destination.glob('*.md'))
        self.assertEqual(1, len(files))
        exported = files[0].read_text(encoding='utf-8')
        self.assertIn('你好，新版 Kiro', exported)
        self.assertIn('你好，已读取对话', exported)
        self.assertIn('Saved:', output.getvalue())
        expected = kiro.SessionParser(kiro.scan_all_sessions()[0]).to_markdown()
        self.assertEqual(expected.encode('utf-8'), files[0].read_bytes(),
                         'Writing on Windows must not double CRLF already present in source text')

    def test_read_errors_are_visible_before_export_filter(self):
        path = self.modern_session()
        path.with_name('messages.jsonl').unlink()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            parsers = kiro._parse_sessions_parallel(kiro.scan_all_sessions())
        self.assertEqual(1, len(parsers))
        self.assertIn('read error', output.getvalue())

    def filter_settings(self, parser, keys):
        with patch.object(kiro, 'read_key', side_effect=keys), contextlib.redirect_stdout(io.StringIO()):
            return kiro.interactive_filter([parser])

    def test_default_and_reset_export_all_output_with_reasoning(self):
        output = '\n'.join('line-' + str(i) for i in range(30))
        parser = self.parse_modern([
            {'type': 'user', 'content': 'Question'},
            {'type': 'assistant', 'operationType': 'Reasoning', 'content': 'Stored reasoning'},
            {'type': 'tool_call', 'toolName': 'execute_pwsh', 'toolCallId': 'call', 'args': {'command': 'example'}},
            {'type': 'tool_result', 'toolCallId': 'call', 'content': output, 'success': True},
        ])
        for keys in (['Q'], ['N', 'D', 'Q'], ['N', '1', 'Q']):
            with self.subTest(keys=keys):
                settings = self.filter_settings(parser, keys)
                self.assertEqual(0, settings[2], 'ALL must be the initial and restored output cap')
                self.assertTrue(settings[0]['reasoning'])
                md = parser.to_markdown(section_filter=settings[0], output_cap=settings[2])
                self.assertIn(output, md)
                self.assertIn('Stored reasoning', md)

    def test_json_preserves_structured_tool_arguments_results_and_unicode(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': '请检查文件'},
            {'type': 'assistant', 'operationType': 'Reasoning', 'content': '记录中的推理'},
            {'type': 'tool_call', 'toolName': 'execute_pwsh', 'toolCallId': 'call-123',
             'args': {'command': 'Write-Output 你好', 'run_in_background': False, 'custom': {'count': 2}}},
            {'type': 'tool_result', 'toolCallId': 'call-123', 'content': '第一行\r\n第二行', 'success': False},
        ])
        document = json.loads(parser.to_json())
        self.assertEqual('kiro-session-export', document['format'])
        self.assertEqual(1, document['schema_version'])
        session = document['sessions'][0]
        self.assertEqual('sess-new-session', session['id'])
        self.assertEqual('/example/project', session['workspace'])
        events = session['events']
        self.assertEqual(['user_message', 'reasoning', 'terminal_cmd', 'terminal_output'],
                         [event['type'] for event in events])
        self.assertEqual('记录中的推理', events[1]['content'])
        self.assertEqual('call-123', events[2]['tool_call_id'])
        self.assertEqual({'count': 2}, events[2]['arguments']['custom'])
        self.assertIs(False, events[2]['arguments']['run_in_background'])
        self.assertEqual(events[2]['tool_call_id'], events[3]['tool_call_id'])
        self.assertIs(False, events[3]['success'])
        self.assertEqual('第一行\r\n第二行', events[3]['output'])
        self.assertEqual('2026-10-28T10:00:00Z', events[0]['ts'])

    def test_json_respects_sections_message_limits_and_does_not_mutate_source(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': 'First question'},
            {'type': 'assistant', 'operationType': 'Say', 'content': 'First answer'},
            {'type': 'assistant', 'operationType': 'Reasoning', 'content': 'First reasoning'},
            {'type': 'user', 'content': 'Second question'},
            {'type': 'assistant', 'operationType': 'Reasoning', 'content': 'Second reasoning'},
        ])
        before = json.dumps(parser.data, ensure_ascii=False)
        document = json.loads(parser.to_json(section_filter={'user_message': True, 'reasoning': True},
                                             user_cap=1, reasoning_cap=1))
        session = document['sessions'][0]
        self.assertNotIn('metadata', session)
        self.assertNotIn('workspace', session)
        self.assertEqual(['Second question', 'Second reasoning'], [e['content'] for e in session['events']])
        self.assertEqual(before, json.dumps(parser.data, ensure_ascii=False))

    def test_json_full_output_and_optional_finite_cap(self):
        output = '\n'.join('line-' + str(i) for i in range(30))
        parser = self.parse_modern([
            {'type': 'user', 'content': 'Question'},
            {'type': 'tool_call', 'toolName': 'fs_write', 'toolCallId': 'call',
             'args': {'path': 'main.py', 'content': output}},
            {'type': 'tool_result', 'toolCallId': 'call', 'content': output, 'success': True},
        ])
        full = json.loads(parser.to_json())['sessions'][0]['events'][-1]
        capped = json.loads(parser.to_json(output_cap=2))['sessions'][0]['events'][-1]
        self.assertEqual(output, full['output'])
        self.assertEqual('... (28 lines trimmed) ...\nline-28\nline-29', capped['output'])
        self.assertEqual(output, parser.data[-1]['output'])
        capped_call = json.loads(parser.to_json(output_cap=2))['sessions'][0]['events'][-2]
        self.assertEqual(output, capped_call['arguments']['content'], 'Tool input arguments must remain exact')

    def test_json_respects_turn_scope_and_omits_image_bytes(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': 'First question'},
            {'type': 'assistant', 'operationType': 'Say', 'content': 'First answer'},
            {'type': 'user', 'content': 'Last question', 'images': [{'data': 'PRIVATE_IMAGE_BYTES'}]},
            {'type': 'assistant', 'operationType': 'Say', 'content': 'Last answer'},
        ])
        parser.trim_to_last_n_turns(1)
        text = parser.to_json()
        self.assertNotIn('First question', text)
        self.assertNotIn('PRIVATE_IMAGE_BYTES', text)
        self.assertIn('[Image', text)
        self.assertEqual(2, len(json.loads(text)['sessions'][0]['events']))

    def test_json_legacy_ide_and_cli_are_supported(self):
        self.legacy_session()
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        self.assertIn('Legacy answer', parser.to_json())
        path = self.write_json(self.cli / 'cli-session.json', {
            'session_id': 'cli-session', 'title': 'CLI question', 'cwd': '/example/project',
        })
        cli_parser = kiro.CliSessionParser(kiro.scan_cli_sessions()[0])
        document = json.loads(cli_parser.to_json())
        self.assertEqual('Kiro CLI', document['sessions'][0]['source'])

    def test_json_ide_metadata_keeps_context_mode_and_lineage(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': 'Question'},
            {'type': 'session_metadata', 'key': 'contextUsage', 'value': {'usagePercentage': 67.5}},
        ])
        parser.parent_session_ids = ['ancestor-session']
        parser.continuation_count = 2
        parser.compaction_count = 1
        session = json.loads(parser.to_json())['sessions'][0]
        self.assertEqual(67.5, session['context_usage_pct'])
        self.assertEqual('Autopilot', session['autonomy_mode'])
        self.assertEqual('vibe', session['session_type'])
        self.assertEqual(['ancestor-session'], session['parent_session_ids'])
        self.assertEqual(2, session['continuation_count'])
        self.assertEqual(1, session['compaction_count'])
        self.assertEqual(['/example/project'], session['metadata']['workspacePaths'])
        self.assertEqual('2026-10-29T10:00:00Z', session['metadata']['lastModifiedAt'])

    def test_json_records_scope_and_source_counts_without_session_metadata(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': 'First'},
            {'type': 'assistant', 'content': 'First answer'},
            {'type': 'user', 'content': 'Second'},
            {'type': 'assistant', 'content': 'Second answer'},
        ])
        parser.trim_to_last_n_turns(1)
        session = json.loads(parser.to_json(section_filter={'user_message': True}))['sessions'][0]
        info = session['export_info']
        self.assertEqual('last', info['scope']['mode'])
        self.assertEqual(1, info['scope']['n'])
        self.assertEqual(2, info['source_turn_count'])
        self.assertEqual(1, info['selected_turn_count'])
        self.assertEqual(4, info['source_event_count'])
        self.assertEqual(2, info['selected_event_count'])
        self.assertEqual(1, info['exported_event_count'])
        self.assertEqual(['agent_message'], info['excluded_sections'])
        self.assertNotIn('metadata', session)
        self.assertNotIn('workspace', session)

    def test_json_records_full_first_range_and_live_scope(self):
        payloads = [
            {'type': 'user', 'content': 'First'},
            {'type': 'assistant', 'operationType': 'Summary', 'content': 'Summary'},
            {'type': 'user', 'content': 'Second'},
            {'type': 'assistant', 'content': 'Second answer'},
        ]
        for scope in (kiro._full_scope(), kiro._first_scope(1), kiro._range_scope(2, 2), kiro._live_scope()):
            with self.subTest(scope=scope):
                parser = self.parse_modern(payloads)
                kiro.apply_extraction_scope(parser, scope)
                info = json.loads(parser.to_json())['sessions'][0]['export_info']
                self.assertEqual(scope, info['scope'])
                self.assertEqual(2, info['source_turn_count'])
                self.assertEqual(5, info['source_event_count'])

    def test_json_explains_ide_limits_and_read_errors_when_errors_are_disabled(self):
        parser = self.parse_modern()
        with parser.entry.messages_file.open('a', encoding='utf-8') as stream:
            stream.write('{broken\n')
        parser = kiro.SessionParser(parser.entry)
        session = json.loads(parser.to_json(section_filter={'user_message': True}))['sessions'][0]
        info = session['export_info']
        self.assertEqual(1, info['read_error_count'])
        self.assertIn('normalized_events_not_raw_backup', info['limitations'])
        self.assertIn('image_data_omitted', info['limitations'])
        self.assertNotIn('nested_sub_executions_not_included', info['limitations'])

    def auxiliary_session(self, marker=None, body='full first\r\nfull second\r\nfull third'):
        marker = marker or "The full output was saved to a file under 'C:/old/session/tool-outputs/shell-123.txt'."
        path = self.modern_session(payloads=[
            {'type': 'user', 'content': 'Question'},
            {'type': 'tool_call', 'toolName': 'execute_pwsh', 'toolCallId': 'call', 'args': {'command': 'example'}},
            {'type': 'tool_result', 'toolCallId': 'call', 'content': marker, 'success': True},
        ])
        output = path.parent / 'tool-outputs' / 'shell-123.txt'
        output.parent.mkdir()
        output.write_bytes(body.encode('utf-8'))
        return path, output, marker, body

    def test_modern_external_output_restores_body_and_preserves_recorded_summary(self):
        path, output, marker, body = self.auxiliary_session()
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        event = json.loads(parser.to_json())['sessions'][0]['events'][-1]
        self.assertEqual(body, event['output'])
        self.assertEqual(marker, event['recorded_output'])
        self.assertEqual([{'file': 'tool-outputs/shell-123.txt', 'status': 'loaded'}], event['external_outputs'])
        self.assertIn(body, parser.to_markdown())
        self.assertEqual(body.encode('utf-8'), output.read_bytes())

    def test_modern_external_output_xml_marker_and_output_cap(self):
        path, _, marker, body = self.auxiliary_session(
            '<file name="tool-outputs/shell-123.txt" language="plaintext" truncated="true">preview</file>')
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        session = json.loads(parser.to_json(output_cap=1))['sessions'][0]
        result = session['events'][-1]
        self.assertEqual('... (2 lines trimmed) ...\nfull third', result['output'])
        self.assertNotIn('full first', parser.to_markdown(output_cap=1))
        self.assertEqual(1, session['export_info']['external_output_files']['loaded'])
        self.assertEqual(body, parser.data[-1]['output'])

    def test_modern_external_output_read_failure_is_visible_with_errors_disabled(self):
        path, output, marker, _ = self.auxiliary_session()
        output.unlink()
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        session = json.loads(parser.to_json(section_filter={'terminal_output': True}))['sessions'][0]
        self.assertEqual(marker, session['events'][0]['output'])
        self.assertEqual('missing', session['events'][0]['external_outputs'][0]['status'])
        self.assertEqual(1, session['export_info']['read_error_count'])

    def test_modern_external_output_cannot_escape_session(self):
        path, output, marker, _ = self.auxiliary_session(
            "The full output was saved to a file under 'tool-outputs/../private.txt'.")
        (path.parent / 'private.txt').write_text('DO_NOT_EXPORT', encoding='utf-8')
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        self.assertNotIn('DO_NOT_EXPORT', parser.to_json())
        self.assertEqual(1, json.loads(parser.to_json())['sessions'][0]['export_info']['read_error_count'])

    def nested_session(self):
        path = self.modern_session(payloads=[
            {'type': 'user', 'content': 'First'},
            {'type': 'sub_agent_start', 'subSessionId': 'child-1', 'parentExecutionId': 'parent-run', 'subAgentName': 'reviewer', 'prompt': 'Review'},
            {'type': 'sub_agent_complete', 'subSessionId': 'child-1', 'parentExecutionId': 'parent-run', 'response': 'Report'},
            {'type': 'user', 'content': 'Second'},
        ])
        nested = path.parent / 'sub-executions' / 'child-1.jsonl'
        nested.parent.mkdir()
        payloads = [
            {'type': 'assistant', 'content': 'Child response'},
            {'type': 'tool_call', 'toolName': 'execute_pwsh', 'toolCallId': 'child-call', 'args': {'command': 'child command'}},
            {'type': 'tool_result', 'toolCallId': 'child-call', 'content': "The full output was saved to a file under 'tool-outputs/child.txt'.", 'success': True},
            {'type': 'tool_call', 'toolName': 'read_file', 'toolCallId': 'read', 'args': {'path': 'private.py'}},
            {'type': 'tool_result', 'toolCallId': 'read', 'content': 'FILTERED_CHILD_READ', 'success': True},
        ]
        nested.write_text(''.join(json.dumps({'id': 'child-message-' + str(i), 'timestamp': '2026-10-28T10:00:00Z', 'payload': p}) + '\n'
                                  for i, p in enumerate(payloads)), encoding='utf-8')
        output = path.parent / 'tool-outputs' / 'child.txt'
        output.parent.mkdir()
        output.write_bytes(b'child first\nchild last')
        return path

    def test_modern_nested_stream_links_to_parent_and_restores_child_output(self):
        self.nested_session()
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        session = json.loads(parser.to_json())['sessions'][0]
        hosts = [e for e in session['events'] if 'sub_execution' in e]
        self.assertEqual(1, len(hosts))
        self.assertEqual('response', hosts[0]['kind'])
        self.assertEqual('parent-run', hosts[0]['execution_id'])
        child = hosts[0]['sub_execution']
        self.assertEqual('child-1', child['id'])
        self.assertEqual('child first\nchild last', child['events'][2]['output'])
        self.assertEqual('child-call', child['events'][2]['tool_call_id'])
        self.assertIn('child first\nchild last', parser.to_markdown())
        self.assertEqual(1, session['export_info']['sub_execution_count'])

    def test_modern_nested_stream_obeys_sections_caps_and_parent_turn_scope(self):
        self.nested_session()
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        sections = {key: key != 'file_read' for key in kiro.ALL_SECTION_KEYS}
        text = parser.to_json(section_filter=sections, output_cap=1)
        self.assertIn('child last', text)
        self.assertNotIn('child first', text)
        self.assertNotIn('FILTERED_CHILD_READ', text)
        md = parser.to_markdown(section_filter=sections, output_cap=1)
        self.assertIn('child last', md)
        self.assertNotIn('child first', md)
        self.assertNotIn('FILTERED_CHILD_READ', md)
        self.assertNotIn('Child response', parser.to_json(section_filter={'user_message': True}))
        parser.trim_to_last_n_turns(1)
        self.assertNotIn('Child response', parser.to_json())

    def test_modern_missing_child_stream_warns_without_losing_parent_report(self):
        path = self.nested_session()
        (path.parent / 'sub-executions' / 'child-1.jsonl').unlink()
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        session = json.loads(parser.to_json())['sessions'][0]
        self.assertIn('Report', parser.to_json())
        self.assertEqual(1, session['export_info']['read_error_count'])

    def test_modern_external_output_invalid_utf8_keeps_notice_and_reports_error(self):
        _, output, marker, _ = self.auxiliary_session()
        output.write_bytes(b'\xff\xfe\x00')
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        session = json.loads(parser.to_json())['sessions'][0]
        result = next(e for e in session['events'] if e.get('result_only'))
        self.assertEqual(marker, result['output'])
        self.assertEqual('unreadable', result['external_outputs'][0]['status'])
        self.assertEqual(1, session['export_info']['external_output_files']['failed'])

    def test_modern_cyclic_child_reference_is_included_only_once(self):
        path = self.nested_session()
        stream = path.parent / 'sub-executions' / 'child-1.jsonl'
        with stream.open('a', encoding='utf-8') as file:
            file.write(json.dumps({'id': 'cycle', 'payload': {
                'type': 'sub_agent_start', 'subSessionId': 'child-1', 'prompt': 'Cycle'}}) + '\n')
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        session = json.loads(parser.to_json())['sessions'][0]
        self.assertEqual(1, session['export_info']['sub_execution_count'])
        statuses = [(e.get('sub_execution') or {}).get('status') for e in kiro._nested_events(session['events'])]
        self.assertEqual(1, statuses.count('already_included'))

    def test_modern_unlinked_child_is_declared_instead_of_assigned_to_wrong_turn(self):
        path = self.modern_session()
        stream = path.parent / 'sub-executions' / 'unlinked.jsonl'
        stream.parent.mkdir()
        stream.write_text(json.dumps({'id': 'orphan', 'payload': {
            'type': 'assistant', 'content': 'UNLINKED_RESPONSE'}}) + '\n', encoding='utf-8')
        parser = kiro.SessionParser(kiro.scan_all_sessions()[0])
        session = json.loads(parser.to_json())['sessions'][0]
        self.assertNotIn('UNLINKED_RESPONSE', parser.to_json())
        self.assertIn('unlinked_sub_executions_not_included', session['export_info']['limitations'])

    def test_json_metadata_toggle_omits_added_private_metadata(self):
        parser = self.parse_modern()
        session = json.loads(parser.to_json(section_filter={'user_message': True}))['sessions'][0]
        for key in ('autonomy_mode', 'context_usage_pct', 'parent_session_ids', 'session_type'):
            self.assertNotIn(key, session)

    def test_json_scope_keeps_source_read_errors_outside_selected_turns(self):
        parser = self.parse_modern([
            {'type': 'user', 'content': 'First'},
            {'type': 'parse_error', 'content': 'damaged record'},
            {'type': 'user', 'content': 'Second'},
        ])
        parser.trim_to_last_n_turns(1)
        info = json.loads(parser.to_json())['sessions'][0]['export_info']
        self.assertEqual(1, info['read_error_count'])
        self.assertEqual(3, info['source_event_count'])
        self.assertEqual(1, info['selected_event_count'])

    def run_json_pipeline(self, entries, answers):
        destination = self.root / 'json-exports'
        destination.mkdir(exist_ok=True)
        settings = ({key: True for key in kiro.ALL_SECTION_KEYS}, False, 0, 0, 0, 0, 0,
                    kiro.default_orch_filter())
        output = io.StringIO()
        with patch('builtins.input', side_effect=answers), \
                patch.object(kiro, 'interactive_filter', return_value=settings), \
                patch.object(kiro, 'choose_output_location', return_value=('single', destination)), \
                patch.object(kiro, 'copy_to_clipboard', return_value=True) as clipboard, \
                patch.object(kiro, 'maybe_open_directory'), contextlib.redirect_stdout(output):
            kiro.process_conversion(','.join(str(i + 1) for i in range(len(entries))), entries, allow_scope=False)
        return destination, clipboard, output.getvalue()

    def test_json_pipeline_separate_files_with_same_title_do_not_overwrite(self):
        self.modern_session('sess-first')
        self.modern_session('sess-second')
        destination, _, output = self.run_json_pipeline(kiro.scan_all_sessions(), ['j', 'f', 's', ''])
        files = list(destination.glob('*.json'))
        self.assertEqual(2, len(files))
        ids = {json.loads(path.read_text(encoding='utf-8'))['sessions'][0]['id'] for path in files}
        self.assertEqual({'sess-first', 'sess-second'}, ids)
        self.assertIn('Saved:', output)

    def test_json_pipeline_combined_file_and_clipboard_remain_valid_json(self):
        self.modern_session('sess-first')
        self.modern_session('sess-second')
        destination, clipboard, _ = self.run_json_pipeline(kiro.scan_all_sessions(), ['j', 'b', 'o', ''])
        files = list(destination.glob('*.json'))
        self.assertEqual(1, len(files))
        document = json.loads(files[0].read_text(encoding='utf-8'))
        self.assertEqual(2, len(document['sessions']))
        self.assertEqual(document, json.loads(clipboard.call_args.args[0]))

    def test_json_pipeline_repeated_exports_preserve_existing_file(self):
        self.modern_session('sess-first')
        entries = kiro.scan_all_sessions()
        destination, _, _ = self.run_json_pipeline(entries, ['j', 'f', ''])
        original = next(destination.glob('*.json'))
        original.write_text('existing export must survive', encoding='utf-8')
        self.run_json_pipeline(entries, ['j', 'f', ''])
        self.assertEqual('existing export must survive', original.read_text(encoding='utf-8'))
        files = [p for p in destination.glob('*.json') if p != original]
        self.assertEqual(1, len(files))
        self.assertEqual('sess-first', json.loads(files[0].read_text(encoding='utf-8'))['sessions'][0]['id'])

    def test_json_pipeline_different_combined_selections_preserve_both_exports(self):
        for sid in ('sess-first', 'sess-second', 'sess-third'):
            self.modern_session(sid)
        entries = {entry.session_id: entry for entry in kiro.scan_all_sessions()}
        destination, _, _ = self.run_json_pipeline(
            [entries['sess-first'], entries['sess-second']], ['j', 'f', 'o', ''])
        self.run_json_pipeline([entries['sess-first'], entries['sess-third']], ['j', 'f', 'o', ''])
        documents = [json.loads(path.read_text(encoding='utf-8')) for path in destination.glob('*.json')]
        self.assertEqual(2, len(documents))
        self.assertEqual({('sess-first', 'sess-second'), ('sess-first', 'sess-third')},
                         {tuple(s['id'] for s in doc['sessions']) for doc in documents})

    def test_export_writer_handles_existing_suffix_and_preserves_unicode(self):
        target = self.root / 'conversation.json'
        target.write_text('original', encoding='utf-8')
        target.with_name('conversation_2.json').write_text('second', encoding='utf-8')
        written = kiro.write_export_file(target, '你好\n')
        self.assertEqual('conversation_3.json', written.name)
        self.assertEqual('你好\n', written.read_text(encoding='utf-8'))
        self.assertEqual('original', target.read_text(encoding='utf-8'))

    def test_concurrent_export_writers_do_not_overwrite(self):
        from concurrent.futures import ThreadPoolExecutor
        target = self.root / 'conversation.json'
        contents = ['export-' + str(i) for i in range(6)]
        with ThreadPoolExecutor(max_workers=6) as executor:
            paths = list(executor.map(lambda content: kiro.write_export_file(target, content), contents))
        self.assertEqual(6, len(set(paths)))
        self.assertEqual(set(contents), {path.read_text(encoding='utf-8') for path in paths})

    def test_json_clipboard_only_multiple_sessions_is_one_document(self):
        self.modern_session('sess-first')
        self.modern_session('sess-second')
        destination, clipboard, _ = self.run_json_pipeline(kiro.scan_all_sessions(), ['j', 'c', ''])
        self.assertEqual([], list(destination.iterdir()))
        self.assertEqual(2, len(json.loads(clipboard.call_args.args[0])['sessions']))

    def test_json_orchestration_excludes_disabled_layers(self):
        parser = self.parse_modern()
        stage = kiro._blank_stage({'name': 'reviewer', 'brief': 'Hidden brief'})
        stage.update(status='finished', report='Kept report', talk='Hidden talk', commands=['Hidden command'])
        parser.data.append({'type': 'orchestration', 'crew_status': 'completed',
                            'task': 'Hidden shared task', 'stages': [stage]})
        text = parser.to_json()
        self.assertIn('Kept report', text)
        for hidden in ('Hidden brief', 'Hidden talk', 'Hidden command', 'Hidden shared task'):
            self.assertNotIn(hidden, text)

    def test_json_chain_export_writes_all_members(self):
        self.modern_session('sess-first')
        self.modern_session('sess-second')
        chain = kiro.Chain('A')
        chain.sessions = kiro.scan_all_sessions()
        destination = self.root / 'chain-exports'
        destination.mkdir()
        settings = ({key: True for key in kiro.ALL_SECTION_KEYS}, False, 0, 0, 0, 0, 0,
                    kiro.default_orch_filter())
        with patch('builtins.input', side_effect=['j', '']), \
                patch.object(kiro, 'interactive_filter', return_value=settings), \
                patch.object(kiro, 'choose_output_location', return_value=('single', destination)), \
                patch.object(kiro, 'maybe_open_directory'), contextlib.redirect_stdout(io.StringIO()):
            kiro.process_chain_export(chain)
        files = list(destination.glob('*.json'))
        self.assertEqual(1, len(files))
        self.assertEqual(2, len(json.loads(files[0].read_text(encoding='utf-8'))['sessions']))


if __name__ == '__main__':
    unittest.main()
