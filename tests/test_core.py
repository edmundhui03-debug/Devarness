"""Portable core controls use synthetic data, never a real user profile."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded

class ReleaseTests(unittest.TestCase):
    def test_current_tree_rejects_personal_values_in_index_and_working_files(self):
        scanner = module('release_check')
        home = 'C:/Users/' + 'privacy-control' + '/notes'
        email = 'privacy-control' + chr(64) + 'contact.dev'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True)
            path = root / 'sample.txt'
            path.write_text(home + '\n' + email, encoding='utf-8')
            subprocess.run(['git', '-C', folder, 'add', '.'], check=True)
            path.write_text('clean working file', encoding='utf-8')
            staged = scanner.scan_tree(root)
            self.assertEqual({item['kind'] for item in staged if item['rule'] == 'personal-value'},
                             {'home path naming a user', 'email address'})
            self.assertNotIn(home, json.dumps(staged))
            self.assertNotIn(email, json.dumps(staged))
            subprocess.run(['git', '-C', folder, 'add', '.'], check=True)
            path.write_text(email, encoding='utf-8')
            self.assertTrue(scanner.scan_tree(root))

    def test_generic_privacy_checks_allow_public_placeholders_without_reading_profiles(self):
        scanner = module('release_check')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True)
            (root / 'readme.txt').write_text(
                'C:/Users/<user>/notes\n/home/runner/project\n'
                'test@example.invalid\n123+noreply@users.noreply.github.com', encoding='utf-8')
            subprocess.run(['git', '-C', folder, 'add', '.'], check=True)
            with patch.object(Path, 'home', side_effect=AssertionError('profile access')):
                self.assertEqual(scanner.scan_tree(root), [])

    def test_personal_symlink_metadata_is_checked_without_opening_its_target(self):
        scanner = module('release_check')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True)
            link = '/home/' + 'privacy-control' + '/private-target'
            oid = subprocess.check_output(['git', '-C', folder, 'hash-object', '-w', '--stdin'],
                                          input=link.encode()).decode().strip()
            subprocess.run(['git', '-C', folder, 'update-index', '--add', '--cacheinfo',
                            '120000', oid, 'link'], check=True)
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('target access')):
                rules = {item['rule'] for item in scanner.scan_tree(root)}
            self.assertIn('personal-value', rules)
            self.assertIn('escaping-symlink', rules)

    def test_outward_working_directory_link_cannot_expose_local_content(self):
        scanner = module('release_check')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'repo'
            outside = Path(folder) / 'excluded'
            root.mkdir()
            outside.mkdir()
            source = root / 'source'
            source.mkdir()
            (source / 'sample.txt').write_text('tracked content', encoding='utf-8')
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            (source / 'sample.txt').unlink()
            source.rmdir()
            (outside / 'sample.txt').write_text('excluded local content', encoding='utf-8')
            try:
                source.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest('Native symlinks unavailable: ' + str(error))
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('excluded content access')):
                findings = scanner.scan_tree(root)
            self.assertIn('escaping-working-path', {item['rule'] for item in findings})

    def test_retained_history_does_not_apply_current_personal_value_policy(self):
        scanner = module('release_check')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def git(*args):
                subprocess.run(['git', '-C', folder, *args], check=True, capture_output=True)
            git('init', '-q')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            path = root / 'readme.txt'
            path.write_text('/home/' + 'privacy-control' + '/notes', encoding='utf-8')
            git('add', '.')
            git('commit', '-qm', 'retained example')
            path.write_text('removed from current source', encoding='utf-8')
            git('add', '.')
            git('commit', '-qm', 'remove example')
            self.assertEqual(scanner.scan_history(root), [])

    def test_personal_dashboard_paths_are_rejected_from_the_release_tree(self):
        scanner = module('release_check')
        paths = ['Harness/dashboard/app/src/App.tsx', 'Harness/bin/dashboard',
                 'Harness/bin/taskboard', 'Harness/taskboard-zh-hk.json',
                 'Library/dashboard/app/src/App.tsx', 'Library/bin/dashboard',
                 'Library/bin/taskboard', 'Library/taskboard-zh-hk.json']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True)
            for relative in paths:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic private feature', encoding='utf-8')
            subprocess.run(['git', '-C', folder, 'add', '.'], check=True)
            rejected = {item['path'] for item in scanner.scan_tree(root)
                        if item['rule'] == 'private-dashboard'}
            self.assertEqual(rejected, set(paths))

    def test_unrelated_visualization_source_is_allowed(self):
        scanner = module('release_check')
        self.assertEqual(scanner.scan_text('app/dashboard.py', 'ordinary source'), [])

    def test_runtime_cache_lock_and_logs_are_rejected_even_if_force_staged(self):
        scanner = module('release_check')
        paths = ['.claude/hooks/task-recall.memo.json', '.claude/hooks/update-tools.lock',
                 '.claude/hooks/update-tools/fixture.log']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(['git', 'init', '-q', folder], check=True)
            for relative in paths:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('synthetic local state', encoding='utf-8')
            subprocess.run(['git', '-C', folder, 'add', '-f', *paths], check=True)
            rejected = {item['path'] for item in scanner.scan_tree(root)
                        if item['rule'] == 'private-runtime-state'}
            self.assertEqual(rejected, set(paths))

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
    @unittest.skipUnless(sys.platform == 'win32', 'Windows Git file-link regression')
    def test_link_skills_repairs_file_links_to_skill_directories(self):
        bootstrap = module('bootstrap')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            source = root / 'Harness/example'
            relative = '.agents/skills/example'
            link = '../../Harness/example'
            path = root / relative
            path.parent.mkdir(parents=True)
            try:
                path.symlink_to(os.path.normpath(link), target_is_directory=False)
            except OSError as error:
                self.skipTest('Native symlinks unavailable: ' + str(error))
            self.assertFalse(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY)
            source.mkdir(parents=True)
            (source / 'SKILL.md').write_text('synthetic skill', encoding='utf-8')
            (root / 'tools').mkdir()
            (root / 'tools/skill-links.json').write_text(
                json.dumps({'links': {relative: link}}), encoding='utf-8')
            with patch.object(bootstrap, 'ROOT', root):
                bootstrap.link_skills()
                bootstrap.link_skills()
            self.assertTrue(path.is_dir())
            self.assertEqual(path.resolve(), source)
            self.assertEqual((path / 'SKILL.md').read_text(encoding='utf-8'), 'synthetic skill')

    def test_manifest_uses_the_harness_directory(self):
        bootstrap = module('bootstrap')
        row = 'Harness/example\thttps://github.com/example/tool.git\t' + 'a' * 40
        self.assertEqual(bootstrap.parse_manifest(row)[0]['path'], 'Harness/example')
        with self.assertRaises(ValueError):
            bootstrap.parse_manifest(row.replace('Harness/', 'Library/'))

    def test_manifest_rejects_escaping_paths_and_authenticated_urls(self):
        bootstrap = module('bootstrap')
        with self.assertRaises(ValueError):
            bootstrap.parse_manifest('../escape\thttps://github.com/a/b.git\t' + 'a' * 40)
        with self.assertRaises(ValueError):
            bootstrap.parse_manifest('Harness/a\thttps://' + 'user:pass' + chr(64) + 'github.com/a/b.git\t' + 'a' * 40)

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
        spec = importlib.util.spec_from_file_location('catalogue', ROOT / 'Harness/library.py')
        library = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(library)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Harness').mkdir()
            (root / 'Harness/repos.txt').write_text(
                'Harness/example\thttps://github.com/example/tool.git\t' + 'a' * 40 + '\n', encoding='utf-8')
            with self.assertRaises(library.Absent):
                library._source_base(root, 'Harness/example/skills', {}, {})
            self.assertEqual(library._source_base(root, 'Harness/typo/skills', {}, {}),
                             root / 'Harness/typo/skills')

if __name__ == '__main__':
    unittest.main()
