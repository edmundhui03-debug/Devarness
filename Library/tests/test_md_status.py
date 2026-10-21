#!/usr/bin/env python3
"""md-format status: the index a machine reads, its memo, and what it does with a file that is not there.

Run: python3 Library/tests/test_md_status.py

The prompt hook asks for this index on every prompt. On 2026-09-22, the day after
Research, DATASET and SAMPLE_FIRMWARE tripled the documents, parsing 1,134 of them took 1.7
seconds each time and the hook had gone from 0.52 s a prompt to 4.1 s. The memo
keeps one file's marked sections until that file changes. It is opt-in: a plain
`md-format status` writes nothing, which is what "read-only" has always meant here.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "Library" / "bin" / "md-format"

DOC = """# {title}

> **2026-09-22** · Peter · `current`
>
> One sentence. Another sentence.

## {head}

`open` · still to do

Prose.
"""


class MemoTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="md-format-memo-")
        self.addCleanup(temp.cleanup)
        self.docs = Path(temp.name) / "docs"
        self.docs.mkdir()
        self.memo = Path(temp.name) / "memo.json"
        self.one = self.docs / "one.md"
        self.one.write_text(DOC.format(title="The first document", head="The first thing waits"),
                            encoding="utf-8")
        (self.docs / "two.md").write_text(
            DOC.format(title="The second document", head="The second thing waits"), encoding="utf-8")

    def status(self, *extra):
        done = subprocess.run([sys.executable, str(TOOL), "status", "--json", *extra, str(self.docs)],
                              capture_output=True, text=True, timeout=120, cwd=str(ROOT),
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        self.assertEqual(done.returncode, 0, done.stderr[:400])
        return json.loads(done.stdout)

    def headings(self, data):
        return sorted(row["heading"] for row in data["sections"])

    def plant(self, heading):
        """Rewrite what the memo holds for one.md, so a run that trusts it says so."""
        data = json.loads(self.memo.read_text(encoding="utf-8"))
        key = next(k for k in data["files"] if k.endswith("one.md"))
        data["files"][key]["rows"][0][2] = heading
        self.memo.write_text(json.dumps(data), encoding="utf-8")

    def test_a_memo_run_says_exactly_what_a_plain_run_says(self):
        plain = self.status()
        self.assertEqual(self.status("--memo", str(self.memo)), plain)     # cold, writes it
        self.assertEqual(self.status("--memo", str(self.memo)), plain)     # warm, reads it

    def test_the_index_carries_each_document_title(self):
        titles = self.status()["titles"]
        self.assertIn("The first document", titles.values())

    def test_an_unchanged_file_is_not_read_again(self):
        self.status("--memo", str(self.memo))
        self.plant("PLANTED IN THE MEMO")
        self.assertIn("PLANTED IN THE MEMO", self.headings(self.status("--memo", str(self.memo))),
                      "the second run re-read a file that had not changed")

    def test_a_changed_file_is_read_again(self):
        self.status("--memo", str(self.memo))
        self.plant("PLANTED IN THE MEMO")
        time.sleep(0.02)
        self.one.write_text(DOC.format(title="The first document", head="The first thing moved on"),
                            encoding="utf-8")
        found = self.headings(self.status("--memo", str(self.memo)))
        self.assertIn("The first thing moved on", found)
        self.assertNotIn("PLANTED IN THE MEMO", found)

    def test_a_memo_from_a_different_parser_is_thrown_away(self):
        self.status("--memo", str(self.memo))
        self.plant("PLANTED IN THE MEMO")
        data = json.loads(self.memo.read_text(encoding="utf-8"))
        data["parser"] = "not-this-md-format"
        self.memo.write_text(json.dumps(data), encoding="utf-8")
        self.assertNotIn("PLANTED IN THE MEMO", self.headings(self.status("--memo", str(self.memo))))

    def test_a_memo_that_cannot_be_read_costs_nothing(self):
        plain = self.status()
        for junk in ("", "not json", "[]", '{"parser": 3, "files": 7}'):
            with self.subTest(junk[:8]):
                self.memo.write_text(junk, encoding="utf-8")
                self.assertEqual(self.status("--memo", str(self.memo)), plain)

    def test_a_tracked_file_that_is_absent_on_this_device_is_counted_not_fatal(self):
        # Ten tracked .md files are symlinks into the Understand-Anything runtime,
        # which a fresh clone has not built. On 2026-09-22 the first of them stopped
        # `md-format status` with a traceback in a worktree — and would on a new device
        # until its bootstrap finished. The index says how many it could not read.
        (self.docs / "gone.md").symlink_to(self.docs / "runtime-not-built" / "gone.md")
        data = self.status()
        self.assertEqual(self.headings(data), ["The first thing waits", "The second thing waits"])
        self.assertEqual(data["counts"]["absent"], 1)

    def test_without_the_flag_nothing_is_written(self):
        before = sorted(p.name for p in self.docs.parent.rglob("*"))
        self.status()
        self.assertEqual(sorted(p.name for p in self.docs.parent.rglob("*")), before)


class HalfMadeCloneTests(unittest.TestCase):
    def test_a_half_made_clone_is_not_checked_as_ours(self):
        # update-tools clones into <path>.partial and renames it only
        # when whole. Until then its files are upstream's, not dev documents.
        temp = tempfile.TemporaryDirectory(prefix="md-format-partial-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / ".claude").mkdir()
        (root / "CLAUDE.md").write_text("", encoding="utf-8")      # how md-format finds its root
        tool = root / "Library" / "bin" / "md-format"
        tool.parent.mkdir(parents=True)
        tool.write_bytes(TOOL.read_bytes())
        nested = root / "Library" / "docling.partial"
        for repo in (root, nested):
            subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, check=True)
        (nested / "README.md").write_text("Upstream's readme, in no house format.\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(nested), "add", "README.md"], capture_output=True, check=True)
        done = subprocess.run([sys.executable, str(tool), "check"], capture_output=True, text=True,
                              timeout=120, cwd=str(root), env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("docling.partial", done.stdout)


if __name__ == "__main__":
    unittest.main()
