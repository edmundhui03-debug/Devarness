"""Ponytail readiness must reject missing source, wrong pins and broken activation."""
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

class PonytailTests(unittest.TestCase):
    def test_checker_exists(self):
        self.assertTrue((ROOT / 'Library/ponytail-check.py').is_file())

    def test_readiness_contract(self):
        script = ROOT / 'Library/ponytail-check.py'
        if not script.exists():
            self.skipTest('checker not implemented yet')
        check = runpy.run_path(str(script))['problems']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(check(root))
            (root / 'Library').mkdir()
            (root / 'Library/repos.txt').write_text('Library/ponytail\thttps://example.invalid/source\t' + 'a'*40 + '\n')
            for path in ('Library/ponytail/skills/ponytail/SKILL.md',
                         'Library/ponytail/skills/ponytail-review/SKILL.md',
                         '.claude/skills/ponytail/SKILL.md', '.agents/skills/ponytail/SKILL.md'):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('fixture')
            (root / 'CLAUDE.md').write_text('.claude/skills/ponytail/SKILL.md')
            with patch('subprocess.check_output', return_value='a'*40+'\n'):
                self.assertEqual(check(root), [])
                (root / '.agents/skills/ponytail/SKILL.md').unlink()
                self.assertTrue(check(root))
            with patch('subprocess.check_output', return_value='b'*40+'\n'):
                self.assertIn('pin mismatch', ';'.join(check(root)))
            (root / 'CLAUDE.md').write_text('no activation')
            self.assertIn('activation', ';'.join(check(root)))

if __name__ == '__main__':
    unittest.main()
