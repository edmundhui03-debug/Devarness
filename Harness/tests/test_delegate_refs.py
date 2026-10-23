#!/usr/bin/env python3
"""delegate's check_refs.py shows each cited line and fails on a dead citation.

Run: python3 Harness/tests/test_delegate_refs.py

The Books checks found eleven `path:line` references in one batch pointing at
lines that had moved while the batch ran (Books/README.md, batch E). A dead
citation must fail the check; a live one must print the line it names.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / ".claude" / "skills" / "delegate" / "check_refs.py"


def run(text):
    with tempfile.TemporaryDirectory(prefix="refs-") as folder:
        note = Path(folder) / "note.md"
        note.write_text(text, encoding="utf-8")
        done = subprocess.run([sys.executable, str(TOOL), str(note)], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
    return done.returncode, done.stdout + done.stderr


class CheckRefsTests(unittest.TestCase):
    def test_a_live_citation_prints_the_line_it_names(self):
        rc, out = run("The template opens with its rule (`Harness/templates/markdown-doc.md:1`).\n")
        self.assertEqual(rc, 0, out)
        self.assertIn("The title is a sentence", out)

    def test_a_missing_file_fails(self):
        rc, out = run("See `Harness/no-such-file.md:3`.\n")
        self.assertEqual(rc, 1, out)
        self.assertIn("missing", out)

    def test_a_line_past_the_end_fails(self):
        rc, out = run("See `Harness/templates/markdown-doc.md:99999`.\n")
        self.assertEqual(rc, 1, out)

    def test_a_file_at_the_root_is_checked_too(self):
        rc, out = run("The router (`CLAUDE.md:99999`).\n")
        self.assertEqual(rc, 1, out)

    def test_a_url_with_a_port_is_not_a_citation(self):
        rc, out = run("The service is on `http://127.0.0.1:47631`.\n")
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
