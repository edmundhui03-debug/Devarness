#!/usr/bin/env python3
"""Every extensionless launcher is pinned to LF in .gitattributes.

Run: python3 Library/tests/test_line_endings.py

`*.sh eol=lf` and `*.py eol=lf` do not reach `Library/bin/i18n` or `md-pages`,
which carry no extension, so each is named on its own line. A name list rots the
moment a launcher is added — agent-memory and new-device were added in
2026-09-17's round and missed — so this test keeps the list and the folder in
step. A launcher checked out with CRLF on the Windows PC fails at its shebang.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
ATTRIBUTES = ROOT / ".gitattributes"
BIN = ROOT / "Library" / "bin"


def pinned_names():
    names = set()
    for line in ATTRIBUTES.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line or "eol=lf" not in line:
            continue
        pattern = line.split()[0]
        if "*" not in pattern and "/" not in pattern:
            names.add(pattern)
    return names


def extensionless_launchers():
    return {path.name for path in BIN.iterdir() if path.is_file() and not path.suffix}


class LineEndingTests(unittest.TestCase):
    def test_every_extensionless_launcher_is_named_with_eol_lf(self):
        missing = sorted(extensionless_launchers() - pinned_names())
        self.assertEqual(missing, [], "add to .gitattributes: " + ", ".join(missing))

    def test_every_named_launcher_still_exists(self):
        # A dropped tool's line outlives it otherwise, as four did in dev's first tree.
        stale = sorted(pinned_names() - extensionless_launchers())
        self.assertEqual(stale, [], "remove from .gitattributes: " + ", ".join(stale))

    def test_the_folder_is_not_empty_so_an_empty_set_cannot_pass_this_by_accident(self):
        self.assertGreaterEqual(len(extensionless_launchers()), 15)
        self.assertIn("start-check", pinned_names())

    def test_a_name_line_is_read_from_the_pattern_column_only(self):
        # "statusline text eol=lf" pins statusline, not "text".
        self.assertNotIn("text", pinned_names())
        self.assertNotIn("eol=lf", pinned_names())


if __name__ == "__main__":
    unittest.main()
