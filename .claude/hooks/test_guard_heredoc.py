#!/usr/bin/env python3
"""The heredoc guard blocks exactly the commands the Bash tool would rewrite.

Run: python3 .claude/hooks/test_guard_heredoc.py

Each case is one the trap produced or one it must not touch. The commands
here carry their backslashes through chr(92), because this file is written
where the trap lives.
"""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

HOOKS = Path(__file__).resolve().parent
BACK = chr(92)


def load():
    loader = importlib.machinery.SourceFileLoader("guard_heredoc", str(HOOKS / "guard_heredoc.py"))
    spec = importlib.util.spec_from_loader("guard_heredoc", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class BodyTests(unittest.TestCase):
    def setUp(self):
        self.guard = load()

    def test_a_body_is_read_to_its_own_terminator(self):
        command = "python3 - <<'PY'\nprint(1)\nPY\necho after"
        self.assertEqual(self.guard.heredoc_bodies(command), ["print(1)"])

    def test_an_indented_terminator_and_a_bare_delimiter_are_read(self):
        command = "cat <<-EOF\n\tone\n\tEOF\ncat << \"OTHER\"\ntwo\nOTHER"
        self.assertEqual(self.guard.heredoc_bodies(command), ["\tone", "two"])

    def test_two_heredocs_on_one_line_each_wait_their_turn(self):
        command = "diff <<A <<B\nfirst\nA\nsecond\nB"
        self.assertEqual(self.guard.heredoc_bodies(command), ["first", "second"])

    def test_a_heredoc_that_is_never_terminated_is_still_a_body(self):
        self.assertEqual(self.guard.heredoc_bodies("cat <<'EOF'\nleft open"), ["left open"])


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.guard = load()

    def blocked(self, command, platform="win32"):
        return self.guard.verdict(command, platform)

    def test_a_backslash_in_a_body_is_blocked_with_the_way_through(self):
        command = "python3 - <<'PY'\ns = s.replace('" + BACK + BACK + "n', 'x')\nPY"
        refusal = self.blocked(command)
        self.assertIsNotNone(refusal)
        self.assertIn("Write or Edit tool", refusal)
        self.assertIn("REMINDERS", refusal)

    def test_the_mac_keeps_its_heredocs(self):
        command = "python3 - <<'PY'\nprint('" + BACK + BACK + "n')\nPY"
        self.assertIsNone(self.blocked(command, platform="darwin"))

    def test_a_body_without_a_backslash_passes(self):
        self.assertIsNone(self.blocked("python3 - <<'PY'\nprint(1)\nPY"))

    def test_a_backslash_outside_every_body_passes(self):
        # The command line itself reaches bash as typed; only a body is rewritten.
        self.assertIsNone(self.blocked('grep -c "C:' + BACK + BACK + 'Users" file.txt'))
        self.assertIsNone(self.blocked("python3 - <<'PY'\nprint(1)\nPY\ngrep 'a" + BACK + "sb' f"))

    def test_a_command_with_no_heredoc_at_all_passes(self):
        self.assertIsNone(self.blocked("echo hello"))

    def test_what_it_cannot_read_passes(self):
        for command in (None, 42, ""):
            self.assertIsNone(self.blocked(command))


class HookTests(unittest.TestCase):
    """The hook contract: exit 2 blocks and explains, everything else exits 0."""

    def run_guard(self, event):
        return subprocess.run([sys.executable, str(HOOKS / "guard_heredoc.py")], input=json.dumps(event),
                              capture_output=True, text=True, timeout=30)

    @unittest.skipUnless(sys.platform == "win32", "the guard blocks only on Windows")
    def test_the_hook_blocks_a_heredoc_that_would_lose_a_backslash(self):
        body = "python3 - <<'PY'\nprint('" + BACK + BACK + "n')\nPY"
        done = self.run_guard({"tool_name": "Bash", "tool_input": {"command": body}})
        self.assertEqual(done.returncode, 2)
        self.assertIn("chr(92)", done.stderr)

    def test_the_hook_lets_an_ordinary_command_through(self):
        done = self.run_guard({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual((done.returncode, done.stderr), (0, ""))

    def test_the_hook_says_nothing_about_what_it_cannot_read(self):
        done = subprocess.run([sys.executable, str(HOOKS / "guard_heredoc.py")], input="not json",
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0)


if __name__ == "__main__":
    unittest.main()
