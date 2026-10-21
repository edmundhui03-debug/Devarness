"""The real launcher must preserve child failures on Windows and POSIX."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

LAUNCHER = Path(__file__).resolve().parents[1] / 'bin/library'


class LauncherTests(unittest.TestCase):
    def test_missing_index_returns_failure_not_success(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, str(LAUNCHER), '--index',
                 str(Path(folder) / 'missing.json'), 'check'],
                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('index missing', result.stderr)

    def test_help_succeeds(self):
        result = subprocess.run([sys.executable, str(LAUNCHER), '--help'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('search', result.stdout)


if __name__ == '__main__':
    unittest.main()
