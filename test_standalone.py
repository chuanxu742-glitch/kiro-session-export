import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import build_standalone


MODULES = ('sections', 'options', 'preferences', 'exporting', 'cli')


class StandaloneBuilderTests(unittest.TestCase):
    def make_project(self, root):
        package = root / 'kiro_export'
        package.mkdir()
        (package / '__init__.py').write_text('', encoding='utf-8')
        (package / 'sections.py').write_text("SECTION = 'from-sections'\n", encoding='utf-8')
        (package / 'options.py').write_text("VALUE = 'from-options'\n", encoding='utf-8')
        (package / 'preferences.py').write_text(
            "from .sections import SECTION\nfrom .options import VALUE\nPREFERENCE = VALUE + '-' + SECTION\n", encoding='utf-8')
        (package / 'exporting.py').write_text(
            'from .preferences import PREFERENCE\nEXPORTED = PREFERENCE\n', encoding='utf-8')
        (package / 'cli.py').write_text(
            'from .exporting import EXPORTED\nCLI_VALUE = EXPORTED\n', encoding='utf-8')
        (root / 'kiro-md.py').write_text(
            'from kiro_export.cli import CLI_VALUE\n'
            "print('standalone:' + CLI_VALUE)\n", encoding='utf-8')

    def test_embedded_bundle_runs_without_source_tree(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as run_dir:
            source_root = Path(source_dir)
            self.make_project(source_root)
            bundle = build_standalone.build_source(source_root)
            script = Path(run_dir) / 'kiro-md.py'
            script.write_text(bundle, encoding='utf-8')

            result = subprocess.run(
                [sys.executable, str(script)], cwd=run_dir, text=True,
                capture_output=True, check=False)

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('standalone:from-options-from-sections', result.stdout.strip())

    def test_standalone_reuses_temporary_settings_and_explicit_scope_wins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / 'copied-kiro-md.py'
            build_standalone.build_standalone(script)

            session = root / 'sessions' / 'workspace-hash' / 'standalone-reuse-check'
            session.mkdir(parents=True)
            (session / 'session.json').write_text(json.dumps({
                'schemaVersion': '1.0.0', 'dataModelVersion': 3,
                'id': 'standalone-reuse-check', 'title': 'Synthetic standalone session',
                'workspacePaths': ['/synthetic/project'], 'rootPaths': ['/synthetic/project'],
                'createdAt': '2026-10-28T10:00:00Z',
                'lastModifiedAt': '2026-10-29T10:00:00Z', 'modelId': 'fixture-model',
                'agentMode': 'vibe', 'autopilot': True,
            }), encoding='utf-8')
            payloads = [
                {'type': 'user', 'content': 'first synthetic prompt'},
                {'type': 'assistant', 'operationType': 'Say', 'content': 'first synthetic reply'},
                {'type': 'user', 'content': 'last synthetic prompt'},
                {'type': 'assistant', 'operationType': 'Say', 'content': 'last synthetic reply'},
            ]
            (session / 'messages.jsonl').write_text(''.join(json.dumps({
                'id': f'message-{index}', 'timestamp': '2026-10-28T10:00:00Z',
                'payload': payload,
            }) + '\n' for index, payload in enumerate(payloads)), encoding='utf-8')
            config = root / 'config' / 'settings.json'
            config.parent.mkdir()
            config.write_text(json.dumps({
                'source': 'ide', 'format': 'json', 'scope': {'mode': 'last', 'n': 1},
            }), encoding='utf-8')
            env = os.environ.copy()
            env.update({
                'KIRO_EXPORT_CONFIG': str(config),
                'KIRO_IDE_SESSIONS_DIR': str(root / 'sessions'),
                'KIRO_HOME': str(root / 'legacy'),
                'KIRO_CLI_SESSIONS_DIR': str(root / 'cli'),
            })
            with tempfile.TemporaryDirectory() as cwd:
                reused = subprocess.run([
                    sys.executable, str(script), 'export', '--session',
                    'standalone-reuse-check', '--output', str(root / 'reuse'), '--reuse',
                ], cwd=cwd, env=env, text=True, capture_output=True, check=False)
                first = subprocess.run([
                    sys.executable, str(script), 'export', '--session',
                    'standalone-reuse-check', '--output', str(root / 'first'),
                    '--reuse', '--first', '1',
                ], cwd=cwd, env=env, text=True, capture_output=True, check=False)

            self.assertEqual(0, reused.returncode, reused.stderr)
            self.assertEqual(0, first.returncode, first.stderr)
            reused_doc = json.loads((root / 'reuse' / 'standalone-reuse-check.json').read_text(encoding='utf-8'))
            first_doc = json.loads((root / 'first' / 'standalone-reuse-check.json').read_text(encoding='utf-8'))
            reused_events = [event.get('content', '') for event in reused_doc['sessions'][0]['events']]
            first_events = [event.get('content', '') for event in first_doc['sessions'][0]['events']]
            self.assertEqual('last', reused_doc['sessions'][0]['export_info']['scope']['mode'])
            self.assertEqual('first', first_doc['sessions'][0]['export_info']['scope']['mode'])
            self.assertIn('last synthetic prompt', reused_events)
            self.assertNotIn('first synthetic prompt', reused_events)
            self.assertIn('first synthetic prompt', first_events)
            self.assertNotIn('last synthetic prompt', first_events)

    def test_build_output_is_deterministic_and_does_not_embed_source_path(self):
        with tempfile.TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            self.make_project(source_root)
            first = build_standalone.build_source(source_root)
            second = build_standalone.build_source(source_root)

        self.assertEqual(first, second)
        self.assertNotIn(source_dir, first)
        self.assertTrue(all(f'kiro_export.{name}' in first for name in MODULES))

    def test_build_does_not_execute_embedded_module_sources(self):
        with tempfile.TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            self.make_project(source_root)
            marker = source_root / 'module-executed'
            code = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
            (source_root / 'kiro_export' / 'sections.py').write_text(code, encoding='utf-8')

            build_standalone.build_source(source_root)

            self.assertFalse(marker.exists())

    def test_default_build_destination_is_dist_script(self):
        with tempfile.TemporaryDirectory() as source_dir:
            source_root = Path(source_dir)
            self.make_project(source_root)
            expected = source_root / 'dist' / 'kiro-md.py'
            written = build_standalone.build_standalone(project_root=source_root)

            self.assertEqual(expected, written)
            self.assertTrue(expected.is_file())

    def test_build_standalone_writes_requested_path(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as output_dir:
            source_root = Path(source_dir)
            self.make_project(source_root)
            output = Path(output_dir) / 'nested' / 'copy.py'
            written = build_standalone.build_standalone(output, project_root=source_root)
            self.assertEqual(output, written)
            self.assertTrue(output.is_file())
            self.assertEqual(build_standalone.build_source(source_root), output.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
