"""library pick and eval-picks: ranked suggestions for a free-text prompt.

Fixture indexes are written by hand, so these run without the YAML parser.
Scores are lexical relevance plus the router's ownership table; they are not
safety or confidence, and nothing here runs a tool.
"""
import hashlib
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'library.py'
DEV = MODULE.parents[1]
FROZEN = Path(__file__).resolve().parent / 'fixtures' / 'library-picks.json'
# Moved once, 2026-10-15: the simplify prompt expects tieitup, which the owner made the coding owner.
FROZEN_SHA256 = '62a3b6b89cbda8cb606da9367f32fe9ab9649fb234972e1f6458e5a1f23ee5e1'
HAS_YAML = importlib.util.find_spec('yaml') is not None


def load():
    spec = importlib.util.spec_from_file_location('dev_library', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(eid, purpose, path, owner_ref='CLAUDE.md|Noise', aliases=(), category='',
          scope='.', mode='library-only'):
    collection, kind, name = eid.split(':')
    return {'id': eid, 'name': name, 'kind': kind, 'collection': collection,
            'purpose': purpose, 'category': category, 'path': path,
            'owner_ref': owner_ref, 'owner': 'fixture', 'scope': scope, 'mode': mode,
            'aliases': list(aliases), 'exclusions': [], 'source_present': True,
            'configured_clients': [], 'runtime_status': 'unknown', 'unfinished': False}


ROUTER = [
    {'file': 'CLAUDE.md', 'domain': 'Building any HTML page', 'owner': '`bilingual-page`; `i18n` for the toggle'},
    {'file': 'CLAUDE.md', 'domain': "Telling the owner's phone an agent finished", 'owner': '`notify` through ntfy'},
    {'file': 'CLAUDE.md', 'domain': 'Literature, paper writing', 'owner': 'claude-scholar, inside a research project only'},
    {'file': 'CLAUDE.md', 'domain': 'Noise', 'owner': 'ECC, library-only'},
] + [  # a router and a catalogue about the size of dev's, so word rarity is realistic
    {'file': 'CLAUDE.md', 'domain': f'Filler domain {n:02d}', 'owner': 'nobody'} for n in range(32)]


def fixture_index():
    entries = [entry(f'filler:skill:helper-{n:03d}', f'Unrelated helper number {n} for other work.',
                     f'Harness/filler/helper-{n:03d}/SKILL.md') for n in range(300)]
    entries += [
        entry('dev:skill:bilingual-page', 'Build a house page with a language toggle.',
              '.claude/skills/bilingual-page/SKILL.md', 'CLAUDE.md|Building any HTML'),
        entry('dev:command:i18n', 'Give a page an English and Cantonese toggle.',
              'Harness/bin/i18n', 'CLAUDE.md|Building any HTML'),
        entry('dev:command:notify', 'Push an alert when an agent finishes work.',
              'Harness/bin/notify', "CLAUDE.md|Telling the owner's phone", aliases=['ntfy']),
        entry('scholar:skill:paper-writing', 'Draft a research paper from literature.',
              'Harness/scholar/paper/SKILL.md', 'CLAUDE.md|Literature', scope='Projects'),
    ]
    # Lexical noise: many entries that repeat the prompt's words in their purpose.
    for n in range(40):
        entries.append(entry(f'ecc:skill:html-report-{n:02d}',
                             'HTML report page builder for dashboards, report pages and HTML exports.',
                             f'Harness/ECC/skills/html-report-{n:02d}/SKILL.md'))
    entries.sort(key=lambda e: e['id'])
    return {'schema': 2, 'fingerprints': {}, 'diagnostics': [], 'router': ROUTER,
            'entries': entries}


class PickTests(unittest.TestCase):
    def setUp(self):
        self.lib = load()
        self.index = fixture_index()

    def ids(self, text, **kw):
        return [p['entry']['id'] for p in self.lib.pick(self.index, text, **kw)]

    def test_the_router_owner_beats_lexical_noise(self):
        self.assertEqual(self.ids('build an HTML report page for the owner')[0],
                         'dev:skill:bilingual-page')

    def test_a_trigger_word_reaches_its_entry(self):
        self.assertIn('dev:command:notify', self.ids('continue and when done push a message on ntfy'))

    def test_the_owner_rows_words_alone_do_not_lift_an_entry_it_does_not_name(self):
        # Cold start: "security scanning" in ECC's row lifted epic-claim for a scanned PDF.
        self.index['router'] = ROUTER + [{'file': 'CLAUDE.md', 'domain': 'Specialist agents, security scanning',
                                          'owner': 'ECC, library-only'}]
        self.index['entries'].append(entry('ecc:command:epic-claim', 'Claim an epic issue, stamp coordination state.',
                                           'Harness/ECC/commands/epic-claim.md', 'CLAUDE.md|Specialist agents'))
        self.index['entries'].sort(key=lambda e: e['id'])
        self.assertNotIn('ecc:command:epic-claim', self.ids('a scanned datasheet with each claim cited'))

    def test_chit_chat_gets_no_picks(self):
        for text in ('hi', 'thanks, that looks great', 'ok', '', '   ', 'the and of'):
            self.assertEqual(self.ids(text), [], text)

    def test_top_limits_the_count_and_order_is_stable(self):
        first = self.ids('build an HTML report page', top=2)
        self.assertEqual(len(first), 2)
        self.assertEqual(first, self.ids('build an HTML report page', top=2))
        with self.assertRaises(ValueError):
            self.lib.pick(self.index, 'html', top=0)

    def test_an_entry_outside_the_project_scope_is_not_picked(self):
        self.assertNotIn('scholar:skill:paper-writing', self.ids('draft a research paper'))
        self.assertIn('scholar:skill:paper-writing',
                      self.ids('draft a research paper', project='Projects/fire'))

    def test_pick_runs_nothing_and_opens_no_connection(self):
        with patch('socket.socket', side_effect=AssertionError('network')), \
                patch('subprocess.Popen', side_effect=AssertionError('subprocess')):
            self.assertTrue(self.ids('build an HTML page'))

    def test_a_reworded_router_still_finds_the_row_by_its_first_words(self):
        self.index['router'][0]['domain'] = 'Building any HTML page, report or dashboard'
        self.assertEqual(self.ids('build an HTML report page')[0], 'dev:skill:bilingual-page')


class PickCliTests(unittest.TestCase):
    def setUp(self):
        self.lib = load()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.index = self.root / 'index.json'
        self.index.write_text(json.dumps(fixture_index()), encoding='utf-8')

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.lib.main(['--root', str(self.root), '--index', str(self.index), *args])
        return code, out.getvalue(), err.getvalue()

    def test_text_lines_name_id_purpose_and_path(self):
        code, out, _ = self.run_cli('pick', 'build an HTML report page', '--top', '2')
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], '1. dev:skill:bilingual-page - Build a house page with a '
                                   'language toggle. - '
                                   + (self.root / '.claude/skills/bilingual-page/SKILL.md').as_posix())

    def test_no_path_leaves_the_file_out(self):
        code, out, _ = self.run_cli('pick', 'build an HTML report page', '--top', '2', '--no-path')
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], '1. dev:skill:bilingual-page - Build a house page with a '
                                              'language toggle.')

    def test_json_lists_the_picks(self):
        code, out, _ = self.run_cli('pick', 'build an HTML report page', '--json')
        self.assertEqual(code, 0)
        picks = json.loads(out)['picks']
        self.assertEqual(picks[0]['id'], 'dev:skill:bilingual-page')
        self.assertLessEqual(len(picks), 3)
        self.assertIn('lexical_score', picks[0])

    def test_no_pick_prints_nothing_and_succeeds(self):
        self.assertEqual(self.run_cli('pick', 'hi'), (0, '', ''))

    def test_a_stale_index_still_answers_with_a_warning(self):
        target = self.root / 'source.md'
        target.write_text('x')
        index = fixture_index()
        index['fingerprints'] = {str(target): 'file:0:0:0:bogus:'}
        self.index.write_text(json.dumps(index), encoding='utf-8')
        code, out, err = self.run_cli('pick', 'build an HTML report page')
        self.assertEqual(code, 0)
        self.assertTrue(out)
        self.assertIn('stale', err)

    def test_a_missing_index_fails(self):
        self.index.unlink()
        code, _, err = self.run_cli('pick', 'build a page')
        self.assertEqual(code, 2)
        self.assertIn('index missing', err)


def picks_set(prompts, mark_key, mark_text):
    return {mark_key: mark_text, 'prompts': prompts}


class EvalPicksTests(unittest.TestCase):
    def setUp(self):
        self.lib = load()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.index = self.root / 'index.json'
        self.index.write_text(json.dumps(fixture_index()), encoding='utf-8')

    def run_set(self, doc, *extra):
        path = self.root / 'set.json'
        path.write_text(json.dumps(doc), encoding='utf-8')
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.lib.main(['--root', str(self.root), '--index', str(self.index),
                                  'eval-picks', str(path), *extra])
        return code, out.getvalue() + err.getvalue()

    FROZEN_STYLE = [
        {'q': 'build an HTML report page', 'any': ['bilingual-page'], 'cold_start': True},
        {'q': 'push the alert on ntfy', 'any': ['notify'], 'reverse': True},
        {'q': 'draft a research paper', 'any': ['scholar']},
    ]

    def test_frozen_style_set_passes_at_its_mark(self):
        doc = picks_set(self.FROZEN_STYLE, '_frozen',
                        'Pass mark: 2 of 3 overall, 1 of the 1 marked cold_start, and both reverse prompts.')
        code, out = self.run_set(doc)
        self.assertEqual(code, 0, out)
        self.assertIn('PASS', out)
        self.assertIn('FAIL', out)
        self.assertIn('2 of 3', out)

    def test_below_the_mark_exits_one(self):
        doc = picks_set(self.FROZEN_STYLE, '_frozen',
                        'Pass mark: 3 of 3 overall, 1 of the 1 marked cold_start, and both reverse prompts.')
        self.assertEqual(self.run_set(doc)[0], 1)

    def test_a_failed_reverse_prompt_fails_the_set(self):
        prompts = self.FROZEN_STYLE + [{'q': 'hi', 'any': ['reverse-skill'], 'reverse': True}]
        doc = picks_set(prompts, '_frozen',
                        'Pass mark: 2 of 4 overall, 1 of the 1 marked cold_start, and every reverse prompt.')
        code, out = self.run_set(doc)
        self.assertEqual(code, 1, out)

    def test_real_style_negatives_are_reported_not_counted(self):
        prompts = [
            {'q': 'build an HTML report page', 'any': ['bilingual-page'], 'kind': 'positive',
             'area': 'Pages'},
            {'q': 'push the alert on ntfy', 'any': ['notify'], 'kind': 'positive',
             'area': 'Reverse engineering'},
            {'q': 'hi', 'any': ['none'], 'kind': 'negative', 'area': 'Negative'},
            {'q': 'build an HTML page', 'any': ['none-in-dev'], 'kind': 'none-in-dev',
             'area': 'Not in dev'},
        ]
        doc = picks_set(prompts, '_pass_mark', 'the set passes at 2 of the 2 positive prompts '
                        'AND every prompt in the reverse-engineering area.')
        code, out = self.run_set(doc, '--report')
        self.assertEqual(code, 0, out)
        self.assertIn('negatives: 1 of 2', out)

    def test_a_set_without_a_readable_pass_mark_is_an_error(self):
        doc = picks_set(self.FROZEN_STYLE, '_frozen', 'no mark here')
        self.assertEqual(self.run_set(doc)[0], 2)

    def test_a_stated_count_that_does_not_match_the_set_is_an_error(self):
        doc = picks_set(self.FROZEN_STYLE, '_frozen',
                        'Pass mark: 2 of 5 overall, 1 of the 1 marked cold_start, and both reverse prompts.')
        code, out = self.run_set(doc)
        self.assertEqual(code, 2, out)
        self.assertIn('5', out)

    def test_the_frozen_fixture_is_unchanged(self):
        self.assertEqual(hashlib.sha256(FROZEN.read_bytes()).hexdigest(), FROZEN_SHA256)


class RealTreeBridge(unittest.TestCase):
    @unittest.skipIf(HAS_YAML, 'already running in a parser-capable interpreter')
    def test_real_tree_in_isolated_runtime(self):
        python = MODULE.parent / '.runtime/library' / (
            'Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.is_file():
            self.skipTest('isolated parser missing; run Harness/setup-library.py --install')
        result = subprocess.run([str(python), str(Path(__file__).resolve()),
                                 'RealTreeTests'], capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(HAS_YAML, 'covered by the isolated parser-runtime bridge')
@unittest.skipUnless((DEV / 'Harness/rea/README.md').is_file()
                     and (DEV / 'Harness/claude-scholar/skills').is_dir()
                     and (DEV / 'Harness/laya').is_dir(),
                     'frozen full-catalogue integration requires optional source checkouts')
class RealTreeTests(unittest.TestCase):
    """The frozen 23-prompt set passes on dev's own index, and pick is fast."""

    def test_frozen_set_passes_and_pick_is_fast(self):
        lib = load()
        with tempfile.TemporaryDirectory() as folder:
            index = str(Path(folder) / 'index.json')
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                lib.main(['--root', str(DEV), '--index', index, 'refresh'])
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(out):
                code = lib.main(['--root', str(DEV), '--index', index, 'eval-picks', str(FROZEN)])
            self.assertEqual(code, 0, out.getvalue())
            start = time.perf_counter()
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                lib.main(['--root', str(DEV), '--index', index, 'pick',
                          'review a KiCad schematic for errors'])
            self.assertLess(time.perf_counter() - start, 1.5)


if __name__ == '__main__':
    unittest.main()
