"""Portable core controls use synthetic data, never a real user profile."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded

class ReleaseTests(unittest.TestCase):
    def test_symlink_targets_are_scanned_before_first_commit(self):
        scanner = module('release_check')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True)
            target = 'gh' + 'p_' + 'z9Vx4B2c' * 5 + '-private-control'
            oid = subprocess.check_output(['git', '-C', folder, 'hash-object', '-w', '--stdin'],
                                          input=target.encode()).decode().strip()
            subprocess.run(['git', '-C', folder, 'update-index', '--add', '--cacheinfo',
                            '120000', oid, 'link'], check=True)
            rules = {item['rule'] for item in scanner.scan_tree(root, ['private-control'])}
            self.assertIn('github-token', rules)
            self.assertIn('private-identifier', rules)

    def test_staged_secret_is_rejected_when_working_file_is_clean(self):
        scanner = module('release_check')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True)
            path = root / 'sample.txt'
            path.write_text('gh' + 'p_' + 'z9Vx4B2c' * 5, encoding='utf-8')
            subprocess.run(['git', '-C', folder, 'add', 'sample.txt'], check=True)
            path.write_text('clean working file', encoding='utf-8')
            self.assertTrue(scanner.scan_tree(root))

    def test_commit_and_tag_messages_are_scanned(self):
        scanner = module('release_check')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                subprocess.run(['git', '-C', folder, *args], check=True, capture_output=True)
            git('init', '-q')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            secret = 'gh' + 'p_' + 'z9Vx4B2c' * 5
            git('commit', '--allow-empty', '-qm', secret)
            git('tag', '-a', 'control', '-m', secret)
            paths = {item['path'] for item in scanner.scan_history(root)}
            self.assertIn('git/commit', paths)
            self.assertIn('control', paths)

    def test_secret_control_is_rejected_without_printing_value(self):
        scanner = module('release_check')
        synthetic = 'gh' + 'p_' + 'q7Xb82Q9' * 5
        findings = scanner.scan_text('example.txt', 'credential=' + synthetic)
        self.assertTrue(findings)
        self.assertNotIn(synthetic, json.dumps(findings))

    def test_private_key_and_project_content_are_rejected(self):
        scanner = module('release_check')
        self.assertTrue(scanner.scan_text('sample.txt', '-----BEGIN ' + 'OPENSSH PRIVATE KEY-----'))
        self.assertTrue(scanner.scan_text('Projects/example/notes.md', 'ordinary prose'))
        self.assertTrue(scanner.scan_text('.env', 'EXAMPLE=unused'))

    def test_nonstandard_literal_and_url_credentials_are_rejected(self):
        scanner = module('release_check')
        self.assertTrue(scanner.scan_text('sample.py', 'API_KEY = "' + 'x8V2p0M7' * 4 + '"'))
        self.assertTrue(scanner.scan_text('sample.txt', 'https://' + 'user:password@example.invalid/a'))
        self.assertFalse(scanner.scan_text('readme.md', 'Use the API_KEY environment variable.'))

    def test_history_catches_a_secret_removed_from_current_tree(self):
        scanner = module('release_check')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                return subprocess.run(['git', '-C', folder, *args], check=True,
                    capture_output=True, text=True)
            git('init', '-q')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            path = root / 'sample.txt'
            path.write_text('gh' + 'p_' + 'a9Bc7D2f' * 5, encoding='utf-8')
            git('add', 'sample.txt')
            git('commit', '-qm', 'control')
            path.write_text('removed', encoding='utf-8')
            git('add', 'sample.txt')
            git('commit', '-qm', 'remove control')
            self.assertTrue(scanner.scan_history(root))

class BootstrapTests(unittest.TestCase):
    def test_manifest_rejects_escaping_paths_and_authenticated_urls(self):
        bootstrap = module('bootstrap')
        with self.assertRaises(ValueError):
            bootstrap.parse_manifest('../escape\thttps://github.com/a/b.git\t' + 'a' * 40)
        with self.assertRaises(ValueError):
            bootstrap.parse_manifest('Library/a\thttps://' + 'user:pass@github.com/a/b.git\t' + 'a' * 40)

    def test_check_has_no_home_or_network_side_effects(self):
        with tempfile.TemporaryDirectory() as folder:
            import os
            env = dict(os.environ, HOME=folder, USERPROFILE=folder)
            result = subprocess.run([sys.executable, str(ROOT / 'tools/bootstrap.py'), '--check'],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_skill_target_cannot_escape_checkout(self):
        bootstrap = module('bootstrap')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                bootstrap.skill_target(Path(folder), '.agents/skills/example', '../../../../outside')

class HookTests(unittest.TestCase):
    def test_claude_hook_returns_current_local_readiness(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/session.py'), '--hook'],
                                input='{}', text=True, capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertIn('START COMPLETE', data['hookSpecificOutput']['additionalContext'])
        self.assertIn('Devarness', data['systemMessage'])

    def test_prompt_hook_needs_no_provider_login(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/session.py'), '--prompt-hook'],
            input=json.dumps({'prompt': 'review this change'}), text=True,
            capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
        self.assertIn('Ponytail', context)
        self.assertIn('CLAUDE.md', context)

class CatalogueTests(unittest.TestCase):
    def test_only_manifest_pins_are_optional_missing_sources(self):
        spec = importlib.util.spec_from_file_location('catalogue', ROOT / 'Library/library.py')
        library = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Library').mkdir()
            (root / 'Library/repos.txt').write_text(
                'Library/example\thttps://github.com/example/tool.git\t' + 'a' * 40 + '\n', encoding='utf-8')
            with self.assertRaises(library.Absent):
                library._source_base(root, 'Library/example/skills', {}, {})
            self.assertEqual(library._source_base(root, 'Library/typo/skills', {}, {}),
                             root / 'Library/typo/skills')

if __name__ == '__main__':
    unittest.main()
