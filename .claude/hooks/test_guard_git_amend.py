#!/usr/bin/env python3
"""Tests for guard_git_amend.py, the PreToolUse hook that stops an amend in the middle of a rebase.

On 2026-09-17 Peter ran `git rebase --continue | tail && git commit --amend`. The pipe hid the
failed continue, HEAD was still the other device's newest commit, and the amend folded that
commit into Peter's. It was caught before the push. Git marks the one moment an amend is right
during a rebase with `rebase-merge/amend`; the hook allows exactly that and nothing else.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

GUARD = Path(__file__).resolve().parent / 'guard_git_amend.py'


class GuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='guard-amend-')
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name) / 'work'
        self.repo.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.com', GIT_EDITOR='true')
        self.git('init', '-q', '-b', 'main')
        self.commit('base.txt', 'base\n', 'base')

    def git(self, *args, check=True):
        return subprocess.run(['git', '-C', str(self.repo), *args], env=self.env, check=check,
                              capture_output=True, text=True)

    def commit(self, name, text, message):
        (self.repo / name).write_text(text)
        self.git('add', name)
        self.git('commit', '-qm', message)

    def stop_at_a_conflict(self):
        self.git('checkout', '-qb', 'mine')
        self.commit('base.txt', 'mine\n', 'mine')
        self.git('checkout', '-q', 'main')
        self.commit('base.txt', 'theirs\n', 'theirs')
        self.git('checkout', '-q', 'mine')
        self.assertNotEqual(self.git('rebase', 'main', check=False).returncode, 0)

    def ask(self, command, tool='Bash', cwd=None):
        event = {'hook_event_name': 'PreToolUse', 'tool_name': tool, 'cwd': str(cwd or self.repo),
                 'tool_input': {'command': command}}
        return subprocess.run([sys.executable, str(GUARD)], input=json.dumps(event), env=self.env,
                              capture_output=True, text=True, timeout=30)

    def test_an_ordinary_amend_is_allowed(self):
        self.assertEqual(self.ask('git commit --amend -m better').returncode, 0)

    def test_an_amend_at_a_stopped_conflict_is_blocked_and_says_why(self):
        self.stop_at_a_conflict()
        done = self.ask('git add base.txt && git commit --amend --no-edit')
        self.assertEqual(done.returncode, 2)
        self.assertIn('rebase', done.stderr)
        self.assertIn('theirs', done.stderr)          # names the commit the amend would have rewritten

    def test_the_repository_is_found_through_cd_and_dash_c(self):
        self.stop_at_a_conflict()
        elsewhere = self.repo.parent
        for command in ('cd "{}" && git commit --amend -F msg.txt'.format(self.repo.as_posix()),
                        'git -C "{}" commit --amend --no-edit'.format(self.repo.as_posix()),
                        'git -C "{}" commit --amend --no-edit'.format(self.repo)):    # backslashes on Windows
            self.assertEqual(self.ask(command, cwd=elsewhere).returncode, 2, command)
        self.assertEqual(self.ask('git -C "{}" commit --amend'.format(self.repo.as_posix()), tool='PowerShell',
                                  cwd=elsewhere).returncode, 2)

    @unittest.skipUnless(os.name == 'nt', "only Git's bash on Windows writes C:/ as /c/")
    def test_the_drive_as_gits_bash_writes_it_is_understood(self):
        self.stop_at_a_conflict()
        path = self.repo.as_posix()
        msys = '/' + path[0].lower() + path[2:]
        self.assertEqual(self.ask('cd "{}" && git commit --amend --no-edit'.format(msys),
                                  cwd=self.repo.parent).returncode, 2)

    def test_an_amend_where_the_rebase_stopped_for_one_is_allowed(self):
        self.commit('two.txt', 'two\n', 'two')
        env = dict(self.env, GIT_SEQUENCE_EDITOR='sed -i -e "1s/^pick/edit/"')
        subprocess.run(['git', '-C', str(self.repo), 'rebase', '-i', 'HEAD~1'], env=env, check=True,
                       capture_output=True, text=True)
        self.assertTrue((self.repo / '.git/rebase-merge/amend').exists())
        self.assertEqual(self.ask('git commit --amend --no-edit').returncode, 0)

    def test_other_commands_and_other_tools_pass_untouched(self):
        self.stop_at_a_conflict()
        self.assertEqual(self.ask('git status && git log --oneline').returncode, 0)
        self.assertEqual(self.ask('echo "git commit --amend is how you reword"', tool='Read').returncode, 0)

    def test_input_it_cannot_read_never_blocks_work(self):
        done = subprocess.run([sys.executable, str(GUARD)], input='not json', capture_output=True, text=True)
        self.assertEqual(done.returncode, 0)


if __name__ == '__main__':
    unittest.main()
