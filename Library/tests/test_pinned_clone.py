#!/usr/bin/env python3
"""bootstrap reproduces every pinned clone, including the sparse ones.

Run: python3 Library/tests/test_pinned_clone.py

`repos.txt` gained a fourth field on 2026-09-20 — the only directories to check
out — because ai-agent-book is 1.5 GB whole and 27 MB as the book text dev reads.
A manifest bootstrap cannot reproduce is a lie in the repository, so these tests
run bootstrap's own `clone_pinned` against a fake git and read back what it was
asked to do. The harness is the one `test_bootstrap_clone.py` uses: lift the
function out of the script rather than copy it, so the two cannot drift.
"""
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2]
BOOTSTRAP = SOURCE / "Library" / "bootstrap.sh"
MANIFEST = SOURCE / "Library" / "repos.txt"
BASH = shutil.which("bash")

# Every call is logged; a clone makes the folder so the caller sees a clone happen.
FAKE_GIT = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GIT_LOG"
for a in "$@"; do
  case "$a" in clone) clone=1 ;; esac
done
if [ -n "${clone:-}" ]; then
  eval "dest=\\${$#}"
  mkdir -p "$dest/.git"
fi
exit 0
"""


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@unittest.skipUnless(BASH, "bash is required")
class ClonePinnedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="pinned-clone-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.log = self.root / "calls.log"
        executable(self.root / "bin" / "git", FAKE_GIT)

    def clone_pinned(self, *args):
        """Run bootstrap's own clone_pinned with the arguments given."""
        text = BOOTSTRAP.read_text(encoding="utf-8")
        match = re.search(r"^clone_pinned\(\) \{.*?^\}", text, re.S | re.M)
        self.assertIsNotNone(match, "bootstrap.sh has no clone_pinned function")
        harness = self.root / "harness.sh"
        quoted = " ".join('"%s"' % a for a in args)
        with harness.open("w", encoding="utf-8", newline="\n") as handle:
            if os.name == "nt":
                # Git Bash prepends its own git during startup.
                handle.write('export PATH="$(cygpath -u "$FAKE_BIN"):$PATH"\n')
            handle.write("say() { printf '   %s\\n' \"$*\"; }\nKB=\"$1\"\n"
                         + match.group(0) + "\nclone_pinned " + quoted + "\n")
        env = dict(os.environ, FAKE_GIT_LOG=str(self.log), FAKE_BIN=str(self.root / "bin"),
                   PATH=os.pathsep.join([str(self.root / "bin"), os.environ.get("PATH", "")]))
        done = subprocess.run([BASH, str(harness), str(self.root / "dev")], env=env,
                              capture_output=True, encoding="utf-8", errors="replace", timeout=60)
        calls = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return done, calls

    def test_a_plain_clone_asks_for_no_sparse_checkout(self):
        done, calls = self.clone_pinned("Library/thing", "https://example.invalid/thing", "abc123")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(any(c.startswith("clone") for c in calls), calls)
        self.assertFalse(any("sparse" in c for c in calls), calls)
        self.assertTrue(any("checkout -q abc123" in c for c in calls), calls)

    def test_a_fourth_field_makes_the_clone_sparse_and_fetches_no_other_blob(self):
        done, calls = self.clone_pinned("Library/book", "https://example.invalid/book", "def456",
                                        "book-en", "book")
        self.assertEqual(done.returncode, 0, done.stderr)
        clone = next(c for c in calls if c.startswith("clone"))
        self.assertIn("--filter=blob:none", clone)
        self.assertIn("--sparse", clone)
        self.assertTrue(any("sparse-checkout set book-en book" in c for c in calls), calls)
        self.assertTrue(any("checkout -q def456" in c for c in calls), calls)

    def test_both_forms_keep_the_four_clone_settings_windows_needs(self):
        for label, args in (("plain", ()), ("sparse", ("book-en",))):
            with self.subTest(label):
                self.setUp()
                _, calls = self.clone_pinned("Library/thing", "https://example.invalid/t", "sha", *args)
                clone = next(c for c in calls if c.startswith("clone"))
                for setting in ("core.autocrlf=false", "core.eol=lf", "core.symlinks=true",
                                "core.longpaths=true"):
                    self.assertIn(setting, clone, label)


class ManifestTests(unittest.TestCase):
    def rows(self):
        for number, line in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip() and not line.startswith("#"):
                yield number, line.split("\t")

    def test_every_row_has_three_or_four_fields_and_a_full_length_commit(self):
        seen = 0
        for number, fields in self.rows():
            seen += 1
            with self.subTest(fields[0]):
                self.assertIn(len(fields), (3, 4), "repos.txt:%d has %d fields" % (number, len(fields)))
                self.assertRegex(fields[2], r"^[0-9a-f]{40}$", "repos.txt:%d" % number)
                self.assertTrue(fields[1].startswith("https://"), "repos.txt:%d" % number)
        self.assertGreater(seen, 20, "the manifest lost rows")

    def test_a_sparse_row_names_directories_that_exist_in_the_clone(self):
        for number, fields in self.rows():
            if len(fields) != 4:
                continue
            clone = SOURCE / fields[0]
            if not (clone / ".git").is_dir():
                self.skipTest("%s is not cloned on this device" % fields[0])
            for wanted in fields[3].split():
                with self.subTest(fields[0] + ":" + wanted):
                    self.assertTrue((clone / wanted).is_dir(),
                                    "repos.txt:%d names %s, absent from the clone" % (number, wanted))

    def test_the_sparse_clone_is_a_fraction_of_the_whole_repository(self):
        book = SOURCE / "Library" / "ai-agent-book"
        if not (book / ".git").is_dir():
            self.skipTest("ai-agent-book is not cloned on this device")
        # 1.5 GB whole on 2026-09-20; the sparse form was 27 MB. A checkout that
        # widened back to everything is worth knowing about on a laptop.
        total = sum(f.stat().st_size for f in book.rglob("*") if f.is_file())
        self.assertLess(total, 400 * 1024 * 1024, "the book clone is no longer sparse")


if __name__ == "__main__":
    unittest.main()
