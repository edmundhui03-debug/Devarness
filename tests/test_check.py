"""Verification faults must stay failures without hiding later checks."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('portable_check', ROOT / 'tools/check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

SUITES = (
    '.claude/hooks/test_guard_git_amend.py',
    '.claude/hooks/test_guard_heredoc.py',
    '.claude/hooks/test_guard_vendor_code.py',
    '.claude/hooks/test_post_edit_check.py',
    'Library/tests/test_line_endings.py',
    'Library/tests/test_delegate_refs.py',
    'Library/tests/test_library.py',
    'Library/tests/test_library_eval.py',
    'Library/tests/test_library_pick.py',
    'Library/tests/test_md_status.py',
    'Library/tests/test_i18n.py',
    'Library/tests/test_publish_check.py',
    'Library/tests/test_vercel_find.py',
    'Library/tests/test_video_study.py',
    'Library/tests/test_tieitup.py',
)


class CheckTests(unittest.TestCase):
    def invoke(self, args=(), first=None):
        output = io.StringIO()
        calls = []

        def execute(command, **kwargs):
            calls.append((command[1:], kwargs['timeout']))
            if len(calls) == 1 and first is not None:
                if isinstance(first, Exception):
                    raise first
                return first
            return subprocess.CompletedProcess(command, 0, 'clean\n', '')

        with mock.patch.object(sys, 'argv', ['check.py', *args]), \
                mock.patch.object(runner.subprocess, 'check_output', return_value=b''), \
                mock.patch.object(runner.subprocess, 'run', side_effect=execute), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                code = runner.main()
            except SystemExit as error:
                code = error.code
            except (OSError, subprocess.TimeoutExpired) as error:
                code = 'uncaught ' + type(error).__name__
        return code, output.getvalue(), calls

    def test_default_preserves_all_commands_and_deadlines(self):
        code, output, calls = self.invoke()
        expected = [(['tools/bootstrap.py', '--check'], 600),
                    (['-m', 'unittest', 'discover', '-s', 'tests', '-v'], 600),
                    (['tools/release_check.py', '--history'], 600)]
        expected += [([path], 900 if path.endswith('/test_tieitup.py') else 600)
                     for path in SUITES]
        self.assertEqual(calls, expected)
        self.assertEqual(code, 0, output)
        self.assertIn('PASS: 18 portable check commands', output)

    def test_timeout_reports_partial_bytes_and_runs_later_checks(self):
        fault = subprocess.TimeoutExpired(['synthetic'], 600,
                                          output=b'partial-out\xff', stderr=b'partial-err')
        code, output, calls = self.invoke(first=fault)
        self.assertEqual(code, 1, output)
        self.assertEqual(len(calls), 18)
        self.assertIn('TIMEOUT', output)
        self.assertIn('partial-out', output)
        self.assertIn('partial-err', output)

    def test_launch_error_is_failure_and_runs_later_checks(self):
        code, output, calls = self.invoke(first=FileNotFoundError('missing test executable'))
        self.assertEqual(code, 1, output)
        self.assertEqual(len(calls), 18)
        self.assertIn('ERROR', output)
        self.assertIn('missing test executable', output)

    def test_nonzero_exit_never_turns_green(self):
        code, output, calls = self.invoke(first=subprocess.CompletedProcess([], 7, '', 'bad check'))
        self.assertEqual(code, 1, output)
        self.assertEqual(len(calls), 18)
        self.assertIn('bad check', output)
        self.assertNotIn('PASS: 18', output)

    def test_selected_rerun_is_partial_and_uses_original_deadline(self):
        code, output, calls = self.invoke(['--only', 'test_tieitup'])
        self.assertEqual(code, 0, output)
        self.assertEqual(calls, [(['Library/tests/test_tieitup.py'], 900)])
        self.assertIn('PARTIAL', output)
        self.assertNotIn('PASS: 18', output)

    def test_failed_selection_remains_partial_and_nonzero(self):
        code, output, calls = self.invoke(['--only', 'test_tieitup'],
                                        subprocess.CompletedProcess([], 2, '', 'failed'))
        self.assertEqual(code, 1, output)
        self.assertEqual(len(calls), 1)
        self.assertIn('PARTIAL', output)

    def test_unknown_selection_is_usage_error_before_execution(self):
        code, output, calls = self.invoke(['--only', 'not_a_suite'])
        self.assertEqual(code, 2, output)
        self.assertEqual(calls, [])

    def test_conflicting_modes_are_rejected_before_execution(self):
        code, output, calls = self.invoke(['--core-only', '--only', 'test_tieitup'])
        self.assertEqual(code, 2, output)
        self.assertEqual(calls, [])

    def test_core_mode_remains_three_commands_and_explicitly_partial(self):
        code, output, calls = self.invoke(['--core-only'])
        self.assertEqual(code, 0, output)
        self.assertEqual(len(calls), 3)
        self.assertIn('PARTIAL', output)


if __name__ == '__main__':
    unittest.main()
