"""TieItUp's skill must cover every Ponytail skill, and readiness must tell ready, stale and missing apart."""
import json
from importlib.util import cache_from_source
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'Harness/tieitup-check.py'
with open(str(ROOT / '.claude/skills/tieitup/references/checked.json'), encoding='utf-8') as _fh:
    PIN = json.load(_fh)['ponytail_commit']


def load():
    return runpy.run_path(str(CHECK))


def stub(root, ponytail, harness, tree='a' * 40):
    """A stand-in for Harness/bin/tieitup with fixed freshness answers."""
    path = Path(root) / 'Harness/bin/tieitup'
    # Same-length rewrites in one second otherwise reuse the previous stub's bytecode.
    Path(cache_from_source(str(path))).unlink(missing_ok=True)
    path.write_text(
        'def ponytail_changes(root):\n    return %r\n'
        'def harness_changes(root):\n    return %r\n'
        'def ponytail_rev(root, rev):\n    return %r\n' % (ponytail, harness, tree), encoding='utf-8')


def make_root(directory):
    root = Path(directory)
    for rel in load()['REQUIRED']:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture', encoding='utf-8')
    (root / 'CLAUDE.md').write_text('load .claude/skills/tieitup/SKILL.md', encoding='utf-8')
    return root


class CounterpartTests(unittest.TestCase):
    def test_every_ponytail_skill_at_the_pin_has_a_row(self):
        names = subprocess.check_output(
            ['git', '-C', str(ROOT / 'Harness/ponytail'), 'ls-tree', '-d', '--name-only', PIN, 'skills/'],
            text=True).split()
        names = [name.split('/')[-1] for name in names]
        self.assertGreaterEqual(len(names), 6)
        skill = (ROOT / '.claude/skills/tieitup/SKILL.md').read_text(encoding='utf-8')
        self.assertEqual(load()['missing_counterparts'](skill, names), [])

    def test_a_removed_row_is_caught(self):
        skill = (ROOT / '.claude/skills/tieitup/SKILL.md').read_text(encoding='utf-8')
        cut = '\n'.join(line for line in skill.splitlines() if not line.startswith('| ponytail-debt |'))
        self.assertEqual(load()['missing_counterparts'](cut, ['ponytail', 'ponytail-debt']), ['ponytail-debt'])


class ReadinessTests(unittest.TestCase):
    def test_missing_review_reference_cannot_report_ready(self):
        reference = '.claude/skills/tieitup/references/review.md'
        with tempfile.TemporaryDirectory() as directory:
            root = make_root(directory)
            (root / reference).unlink(missing_ok=True)
            self.assertEqual(load()['problems'](root), ['missing ' + reference])

    def test_complete_root_has_no_problems(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load()['problems'](make_root(directory)), [])

    def test_each_missing_file_is_named(self):
        check = load()
        for rel in check['REQUIRED']:
            with tempfile.TemporaryDirectory() as directory:
                root = make_root(directory)
                (root / rel).unlink()
                self.assertEqual(check['problems'](root), ['missing ' + rel])

    def test_router_must_name_the_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_root(directory)
            (root / 'CLAUDE.md').write_text('load .claude/skills/ponytail/SKILL.md', encoding='utf-8')
            self.assertEqual(load()['problems'](root), ['router does not name .claude/skills/tieitup/SKILL.md'])

    def test_stale_joins_the_commands_reasons_and_missing_counterparts(self):
        check = load()
        with tempfile.TemporaryDirectory() as directory:
            root = make_root(directory)
            (root / '.claude/skills/tieitup/SKILL.md').write_text('| ponytail | x | y |\n| ponytail-review | x | y |\n',
                                                                encoding='utf-8')
            for name in ('ponytail', 'ponytail-new'):
                (root / 'Harness/ponytail/skills' / name).mkdir(parents=True, exist_ok=True)
            stub(root, ['skills moved'], ['harness moved'])
            self.assertEqual(check['stale'](root), ['skills moved',
                                                    'Ponytail skill ponytail-new has no TieItUp counterpart',
                                                    'harness moved'])
            stub(root, [], [])
            (root / 'Harness/ponytail/skills/ponytail-new').rmdir()
            self.assertEqual(check['stale'](root), [])

    def test_an_unreadable_command_is_stale_not_a_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            reasons = load()['stale'](make_root(directory))
            self.assertEqual(len(reasons), 1)
            self.assertTrue(reasons[0].startswith('TieItUp command unreadable'), reasons)


class NotifyTests(unittest.TestCase):
    """After update-tools moves Ponytail, one needs-owner alert per new skills tree, and never a failure."""

    def setUp(self):
        self.sent = []
        self.answer = 0

    def send(self, root, message):
        self.sent.append(message)
        return self.answer

    def test_one_alert_per_skills_tree(self):
        check = load()
        with tempfile.TemporaryDirectory() as directory:
            root = make_root(directory)
            stub(root, ["Ponytail's skills changed"], [], tree='t1' * 20)
            self.assertEqual(check['notify_owner'](root, self.send), 0)
            self.assertEqual(check['notify_owner'](root, self.send), 0)
            self.assertEqual(len(self.sent), 1)
            self.assertIn('t1t1t1t', self.sent[0])
            stub(root, ["Ponytail's skills changed"], [], tree='t2' * 20)
            check['notify_owner'](root, self.send)
            self.assertEqual(len(self.sent), 2)

    def test_a_failed_alert_is_tried_again(self):
        check = load()
        with tempfile.TemporaryDirectory() as directory:
            root = make_root(directory)
            stub(root, ["Ponytail's skills changed"], [])
            self.answer = 1
            self.assertEqual(check['notify_owner'](root, self.send), 0)
            self.answer = 0
            check['notify_owner'](root, self.send)
            self.assertEqual(len(self.sent), 2)

    def test_nothing_changed_sends_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = make_root(directory)
            stub(root, [], [])
            self.assertEqual(load()['notify_owner'](root, self.send), 0)
            self.assertEqual(load()['notify_owner'](make_root(directory + '/broken'), self.send), 0)
            self.assertEqual(self.sent, [])

    def test_proposals_come_from_the_command(self):
        check = load()
        with tempfile.TemporaryDirectory() as directory:
            root = make_root(directory)
            self.assertEqual(check['proposals'](root), 0)
            (root / 'Harness/bin/tieitup').write_text(
                'def proposals(home, root):\n    return ["narrow x", "silent y"]\n', encoding='utf-8')
            self.assertEqual(check['proposals'](root), 2)

    def test_live_repository_is_ready_or_stale(self):
        check = load()
        if check['problems'](ROOT):
            self.skipTest('TieItUp is not fully installed in this checkout yet')
        self.assertIsInstance(check['stale'](ROOT), list)


if __name__ == '__main__':
    unittest.main()
