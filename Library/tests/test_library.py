"""Offline library contracts; fixture data never reads real client settings."""
import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'library.py'


def load():
    spec = importlib.util.spec_from_file_location('dev_library', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HAS_YAML = importlib.util.find_spec('yaml') is not None


class ParserRuntimeTests(unittest.TestCase):
    @unittest.skipIf(HAS_YAML, 'already running in a parser-capable interpreter')
    def test_isolated_refresh_fixtures(self):
        python = MODULE.parent / '.runtime/library' / (
            'Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.assertTrue(python.is_file(), 'Run Library/setup-library.py --install first')
        self.assertNotEqual(Path(sys.executable).resolve(), python.resolve(),
                            'The isolated parser runtime is missing PyYAML')
        result = subprocess.run([str(python), str(Path(__file__).resolve())],
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(HAS_YAML, 'covered by isolated parser-runtime bridge')
class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.lib = load()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'CLAUDE.md').write_text('| Domain | Owner |\n| Python development | ECC |\n')
        self.sources = [{'collection': 'ecc', 'kind': 'skill', 'root': 'vendor',
                         'pattern': '*/SKILL.md', 'scope': '.',
                         'owner_ref': 'CLAUDE.md|Python development'}]
        self.policy = {'entries': {}}
        self.skill('python-testing', 'Use pytest for Python tests')

    def skill(self, name, purpose, extra=''):
        p = self.root / 'vendor' / name / 'SKILL.md'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('---\nname: ' + name + '\ndescription: ' + json.dumps(purpose)
                     + '\n' + extra + '---\n# Useful skill\n', encoding='utf-8')
        return p

    def index(self):
        return self.lib.build_index(self.root, self.sources, self.policy)

    def test_index_is_stable_and_valid(self):
        index = self.index()
        self.assertEqual(index, self.index())
        self.assertEqual(self.lib.validate_index(index), [])
        self.assertEqual(index['entries'][0]['id'], 'ecc:skill:python-testing')
        self.assertEqual(index['entries'][0]['mode'], 'library-only')
        self.assertEqual(index['entries'][0]['runtime_status'], 'unknown')

    def test_scoped_entry_never_wins_outside_its_project(self):
        self.skill('paper', 'Python pytest tests review paper citations')
        self.policy['entries']['ecc:skill:paper'] = {'scope': 'Research'}
        index = self.index()
        hits = self.lib.search(index, 'paper citations', '.', 'codex')
        self.assertEqual(hits, [])
        self.assertEqual(self.lib.search(index, 'paper citations', 'Research/case',
                                         'codex')[0]['entry']['name'], 'paper')
        self.assertEqual(self.lib.search(index, 'paper citations', 'Research-other',
                                         'codex'), [])

    def test_empty_and_unmatched_queries_are_empty(self):
        for query in ('', '   ', 'zzzz-no-match'):
            self.assertEqual(self.lib.search(self.index(), query, '.', 'codex'), [])

    def test_exact_name_wins_and_ties_are_stable(self):
        self.skill('aaa', 'Python tests')
        index = self.index()
        hits = self.lib.search(index, 'python-testing', '.', 'codex')
        self.assertEqual(hits[0]['entry']['id'], 'ecc:skill:python-testing')
        self.assertEqual(hits, self.lib.search(index, 'python-testing', '.', 'codex'))

    def test_duplicate_names_in_collections_are_distinct(self):
        second = dict(self.sources[0], collection='other')
        index = self.lib.build_index(self.root, self.sources + [second], self.policy)
        self.assertEqual(len({e['id'] for e in index['entries']}), 2)

    def test_bad_yaml_is_diagnostic_not_healthy(self):
        p = self.skill('bad', 'x')
        p.write_text('---\nname: bad\ndescription: bad: colon\n---\n')
        index = self.index()
        self.assertTrue(index['diagnostics'])
        self.assertTrue(self.lib.validate_index(index))
        self.assertNotIn('bad', [e['name'] for e in index['entries']])

    def test_duplicate_keys_and_custom_tags_are_rejected(self):
        for body in ('name: bad\nname: worse\ndescription: text\n',
                     'name: bad\ndescription: !!python/object:os.system {}\n'):
            self.skill('bad', 'x').write_text('---\n' + body + '---\n')
            self.assertTrue(self.index()['diagnostics'])

    def test_block_description_and_missing_sources(self):
        p = self.skill('block', 'unused')
        p.write_text('---\nname: block\ndescription: >\n  Python\n  tests\n---\n')
        index = self.index()
        entry = next(e for e in index['entries'] if e['name'] == 'block')
        self.assertEqual(entry['purpose'].strip(), 'Python tests')
        self.sources[0]['root'] = 'missing'
        self.assertTrue(self.index()['diagnostics'])

    def test_unreadable_source_root_is_diagnostic_not_a_crash(self):
        # A Windows file symlink to a directory raises WinError 5 on is_dir().
        with patch.object(self.lib.Path, 'is_dir', side_effect=PermissionError('denied')):
            index = self.index()
        self.assertTrue(any('missing or not a directory' in d for d in index['diagnostics']))

    def test_large_file_and_missing_owner_are_diagnostic(self):
        self.skill('huge', 'x').write_text('x' * 65537)
        self.assertTrue(self.index()['diagnostics'])
        (self.root / 'CLAUDE.md').write_text('no owner table')
        self.assertTrue(self.index()['diagnostics'])

    def test_owner_row_is_found_by_its_first_words_after_rewording(self):
        (self.root / 'CLAUDE.md').write_text(
            '| Name | Leads |\n| --- | --- |\n| Python development | not the router |\n\n'
            '| Domain | Owner |\n| --- | --- |\n'
            '| Python development, testing and packaging | ECC |\n')
        index = self.index()
        self.assertEqual(index['diagnostics'], [])
        self.assertEqual(index['entries'][0]['owner'], 'ECC')
        self.assertEqual(index['router'], [{'file': 'CLAUDE.md', 'owner': 'ECC',
                                            'domain': 'Python development, testing and packaging'}])

    def test_a_missing_or_ambiguous_owner_row_is_a_clear_diagnostic(self):
        (self.root / 'CLAUDE.md').write_text('| Domain | Owner |\n| --- | --- |\n'
                                             '| Ruby development | x |\n')
        self.assertIn("no ownership-table row in CLAUDE.md starts with 'Python development'",
                      ' '.join(self.index()['diagnostics']))
        (self.root / 'CLAUDE.md').write_text('| Domain | Owner |\n| --- | --- |\n'
                                             '| Python development tools | x |\n'
                                             '| Python development guides | y |\n')
        self.assertIn('matches 2 ownership-table rows', ' '.join(self.index()['diagnostics']))

    def test_owner_ref_key_must_end_at_a_word_boundary(self):
        (self.root / 'CLAUDE.md').write_text('| Domain | Owner |\n| --- | --- |\n'
                                             '| Python developments | x |\n')
        self.assertTrue(self.index()['diagnostics'])

    def test_in_progress_entries_remain_searchable_and_labelled(self):
        self.skill('in-progress', 'experimental useful tool')
        index = self.index()
        entry = next(e for e in index['entries'] if e['name'] == 'in-progress')
        self.assertTrue(entry['unfinished'])
        self.assertTrue(self.lib.search(index, 'experimental', '.', 'codex'))

    def test_recursive_source_glob_indexes_nested_commands(self):
        self.sources[0].update(kind='command', pattern='**/*.md')
        p = self.root / 'vendor' / 'nested' / 'commands' / 'example.md'
        p.parent.mkdir(parents=True)
        p.write_text('# Example nested command\n')
        index = self.index()
        self.assertFalse(index['diagnostics'])
        self.assertIn('ecc:command:example', [e['id'] for e in index['entries']])

    def test_large_command_with_short_metadata_is_indexed(self):
        self.sources[0].update(kind='command', pattern='tool')
        p = self.root / 'vendor/tool'
        p.write_text('#!/usr/bin/env python3\n\"\"\"A useful command.\"\"\"\n' + '# body\n' * 20000)
        index = self.index()
        self.assertEqual(index['diagnostics'], [])
        self.assertEqual(index['entries'][0]['purpose'], 'A useful command.')

    def test_query_does_not_execute_or_connect(self):
        index = self.index()
        with patch('socket.socket', side_effect=AssertionError('network')), \
                patch('subprocess.Popen', side_effect=AssertionError('subprocess')):
            self.assertTrue(self.lib.search(index, 'pytest', '.', 'codex'))

    def test_invalid_limit_and_project_are_rejected(self):
        for limit in (0, 21, -1):
            with self.assertRaises(ValueError):
                self.lib.search(self.index(), 'Python', '.', 'codex', limit)
        with self.assertRaises(ValueError):
            self.lib.search(self.index(), 'Python', '../outside', 'codex')

    def test_missing_owner_is_not_eligible(self):
        (self.root / 'CLAUDE.md').write_text('no ownership table')
        self.assertEqual(self.lib.search(self.index(), 'pytest', '.', 'codex'), [])

    def test_stop_words_do_not_create_spurious_matches(self):
        self.skill('words', 'the and of one with')
        self.assertEqual(self.lib.search(self.index(), 'the and of', '.', 'codex'), [])

    def test_registry_resolves_the_matching_project_not_another_project(self):
        registry = self.root / 'registry.json'
        registry.write_text(json.dumps({'plugins': {'test@market': [
            {'scope': 'local', 'projectPath': str(self.root / 'other'),
             'installPath': str(self.root / 'wrong')},
            {'scope': 'user', 'installPath': str(self.root / 'vendor')}
        ]}}))
        self.sources[0]['root'] = '@plugin:test@market'
        with patch.object(self.lib, 'REGISTRY', registry, create=True):
            index = self.index()
        self.assertEqual(index['diagnostics'], [])
        self.assertEqual(len(index['entries']), 1)

    def test_ambiguous_registry_is_not_silently_selected(self):
        registry = self.root / 'registry.json'
        row = {'scope': 'user', 'installPath': str(self.root / 'vendor')}
        registry.write_text(json.dumps({'plugins': {'test@market': [row, row]}}))
        self.sources[0]['root'] = '@plugin:test@market'
        with patch.object(self.lib, 'REGISTRY', registry, create=True):
            self.assertTrue(self.index()['diagnostics'])

    def plugin_source(self):
        self.sources.insert(0, {'collection': 'plug', 'kind': 'skill', 'root': '@plugin:test@market',
                                'pattern': '*/SKILL.md', 'scope': '.',
                                'owner_ref': 'CLAUDE.md|Python development'})
        self.policy['entries']['plug:skill:finishing'] = {'aliases': ['finish']}

    def test_a_plugin_not_installed_is_a_note_and_the_index_stays_healthy(self):
        # A new device before the owner installs the plugin: no registry at all.
        self.plugin_source()
        with patch.object(self.lib, 'REGISTRY', self.root / 'no-registry.json', create=True):
            index = self.index()
        self.assertEqual(index['diagnostics'], [])
        self.assertEqual(len(index['notes']), 2, index['notes'])
        self.assertEqual(self.lib.validate_index(index), [])
        self.assertTrue(self.lib.search(index, 'pytest', '.', 'codex'))

    def test_a_plugin_missing_from_a_present_registry_is_a_note(self):
        registry = self.root / 'registry.json'
        registry.write_text(json.dumps({'plugins': {}}))
        self.plugin_source()
        with patch.object(self.lib, 'REGISTRY', registry, create=True):
            index = self.index()
        self.assertEqual(index['diagnostics'], [])
        self.assertTrue(index['notes'])

    def test_a_broken_registry_is_still_a_diagnostic(self):
        registry = self.root / 'registry.json'
        registry.write_text('not json')
        self.plugin_source()
        with patch.object(self.lib, 'REGISTRY', registry, create=True):
            self.assertTrue(self.index()['diagnostics'])

    def test_policy_for_an_unknown_entry_of_a_present_source_is_a_diagnostic(self):
        self.policy['entries']['ecc:skill:no-such-skill'] = {'aliases': ['x']}
        self.assertTrue(self.index()['diagnostics'])

    def test_cli_check_passes_with_only_notes(self):
        self.plugin_source()
        library = self.root / 'Library'
        library.mkdir()
        (library / 'library-sources.json').write_text(json.dumps(self.sources))
        (library / 'library-policy.json').write_text(json.dumps(self.policy))
        out = io.StringIO()
        with patch.object(self.lib, 'REGISTRY', self.root / 'no-registry.json', create=True), \
                redirect_stdout(out):
            self.assertEqual(self.lib.main(['--root', str(self.root), 'refresh']), 0)
            self.assertEqual(self.lib.main(['--root', str(self.root), 'check']), 0)
            self.assertEqual(self.lib.main(['--root', str(self.root), 'search', 'pytest']), 0)
        self.assertIn('note:', out.getvalue())

    def test_invalid_activation_mode_is_diagnostic(self):
        self.policy['entries']['ecc:skill:python-testing'] = {'mode': 'magical'}
        self.assertTrue(self.index()['diagnostics'])

    def test_cli_missing_index_returns_json_error(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.lib.main(['--root', str(self.root), 'search', 'pytest', '--json'])
        self.assertEqual(code, 2)
        self.assertIn('error', json.loads(out.getvalue()))

    def test_refresh_then_source_edit_is_stale(self):
        library = self.root / 'Library'
        library.mkdir()
        (library / 'library-sources.json').write_text(json.dumps(self.sources))
        (library / 'library-policy.json').write_text(json.dumps(self.policy))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lib.main(['--root', str(self.root), 'refresh', '--json']), 0)
        self.skill('new-skill', 'new tool')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(self.lib.main(['--root', str(self.root), 'search', 'pytest', '--json']), 2)

    def test_bytecode_cache_after_refresh_is_not_stale(self):
        # Tests import Library/bin scripts, and Python writes __pycache__ beside
        # them; the 2026-10-10 daily check failed on exactly that.
        library = self.root / 'Library'
        library.mkdir()
        (library / 'library-sources.json').write_text(json.dumps(self.sources))
        (library / 'library-policy.json').write_text(json.dumps(self.policy))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lib.main(['--root', str(self.root), 'refresh', '--json']), 0)
        (self.root / 'vendor' / '__pycache__').mkdir()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(self.lib.main(['--root', str(self.root), 'search', 'pytest', '--json']), 0)

    def test_recursive_yaml_alias_is_rejected_as_metadata_not_expanded(self):
        self.skill('recursive', 'x').write_text(
            '---\nname: recursive\ndescription: &loop [*loop]\n---\n')
        index = self.index()
        self.assertTrue(index['diagnostics'])
        self.assertNotIn('recursive', [e['name'] for e in index['entries']])

    def test_cli_query_cannot_run_processes_or_network(self):
        library = self.root / 'Library'
        library.mkdir()
        (library / 'library-sources.json').write_text(json.dumps(self.sources))
        (library / 'library-policy.json').write_text(json.dumps(self.policy))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(self.lib.main(['--root', str(self.root), 'refresh']), 0)
        with patch('socket.socket', side_effect=AssertionError('network')), \
                patch('subprocess.Popen', side_effect=AssertionError('subprocess')), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(self.lib.main(['--root', str(self.root), 'search', 'pytest']), 0)

    def test_setup_card_is_indexed_as_a_guide_to_usage_details(self):
        folder = self.root / 'Library/setup'
        folder.mkdir(parents=True)
        card = folder / 'example-tool.md'
        card.write_text('# Compress build logs for scoped diagnosis\n\n'
                        '| Invocation | example-tool --input log.txt |\n'
                        '| Prerequisites | Python |\n'
                        '| Do not use when | source log must stay unmodified |\n')
        self.sources = [dict(self.sources[0], collection='setup', kind='guide',
                             root='Library/setup', pattern='*.md')]
        index = self.index()
        self.assertEqual(index['diagnostics'], [])
        result = self.lib.search(index, 'Compress build logs', '.', 'codex')[0]['entry']
        self.assertEqual(result['path'], 'Library/setup/example-tool.md')
        self.assertEqual(result['purpose'], 'Compress build logs for scoped diagnosis')
        self.assertNotIn('log.txt', result['purpose'])

    def test_index_validation_rejects_duplicate_ids(self):
        index = self.index()
        index['entries'].append(dict(index['entries'][0]))
        self.assertTrue(self.lib.validate_index(index))


if __name__ == '__main__':
    unittest.main()
