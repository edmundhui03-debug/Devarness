"""Real child processes exercise the runner's bounded failure boundary."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('check_process', ROOT / 'tools/check.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ProcessTests(unittest.TestCase):
    def check(self, command, timeout=5):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            passed = runner.run_check(command, timeout)
        return passed, output.getvalue()

    def test_real_timeout_keeps_partial_output_and_next_command_can_run(self):
        command = [sys.executable, '-c',
                   "import time; print('started', flush=True); time.sleep(30)"]
        # Allow interpreter startup under load before testing captured timeout output.
        passed, output = self.check(command)
        self.assertFalse(passed)
        self.assertIn('TIMEOUT', output)
        self.assertIn('started', output)
        passed, output = self.check([sys.executable, '-c', "print('next check')"])
        self.assertTrue(passed, output)
        self.assertIn('next check', output)

    def test_real_nonzero_exit_keeps_stderr_and_is_failure(self):
        passed, output = self.check([sys.executable, '-c',
                                    "import sys; print('failure reason', file=sys.stderr); sys.exit(7)"])
        self.assertFalse(passed)
        self.assertIn('FAIL', output)
        self.assertIn('failure reason', output)

    def test_missing_executable_reports_error_without_raising(self):
        with tempfile.TemporaryDirectory() as folder:
            passed, output = self.check([str(Path(folder) / 'absent-executable')])
        self.assertFalse(passed)
        self.assertIn('ERROR', output)


if __name__ == '__main__':
    unittest.main()
