"""amend, inline_reader and linked_run: the helpers Peter and Aster use around a harness step."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import amend  # noqa: E402
import inline_reader  # noqa: E402
import linked_run  # noqa: E402


def page(body, zh):
    box = '<script id="i18n-zh" type="application/json">' + json.dumps(zh, ensure_ascii=False) + "</script>"
    return "<style>x</style>\n<!doctype html>\n<meta charset=\"utf-8\">\n" + body + box


class AmendTests(unittest.TestCase):
    def test_edit_replaces_once_and_refuses_a_missing_or_repeated_string(self):
        self.assertEqual(amend.edit("<p>a</p>", [["a", "b"]]), "<p>b</p>")
        with self.assertRaises(SystemExit):
            amend.edit("<p>a</p>", [["zzz", "b"]])
        with self.assertRaises(SystemExit):
            amend.edit("a a", [["a", "b"]])

    def test_missing_lists_only_untranslated_keys(self):
        text = page('<li data-i18n="old-1">Old</li><li data-i18n="new-2">New</li>', {"old-1": "舊"})
        self.assertEqual(amend.missing(text), {"new-2": "New"})

    def test_merge_keeps_used_keys_drops_unused_and_counts_the_rest(self):
        text = page('<li data-i18n="old-1">Old</li><li data-i18n="new-2">New</li><p data-i18n="gap-3">G</p>',
                    {"old-1": "舊", "gone-9": "已刪"})
        merged, untranslated = amend.merge(text, {"new-2": "新"})
        self.assertEqual(merged, {"old-1": "舊", "new-2": "新"})
        self.assertEqual(untranslated, 1)

    def test_a_page_without_a_dictionary_is_refused(self):
        with self.assertRaises(SystemExit):
            amend.missing("<p data-i18n='a'>x</p>")

    def test_head_puts_doctype_and_charset_first_exactly_once(self):
        fixed = amend.head(page("<p>x</p>", {}))
        self.assertTrue(fixed.startswith('<!doctype html>\n<meta charset="utf-8">\n<style>'))
        self.assertEqual(fixed.count("<!doctype html>"), 1)

    def test_head_removes_the_pairs_inject_leaves_after_the_toggle(self):
        stray = '\n<meta charset="utf-8"/>\n<!DOCTYPE html>\n'
        fixed = amend.head(page("<p>x</p>" + stray * 2, {}))
        self.assertEqual(fixed.lower().count("<!doctype html>"), 1)
        self.assertEqual(fixed.count("charset="), 1)
        self.assertIn("<p>x</p>", fixed)

    def test_main_round_trip_on_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            html, pairs, zh, out = (Path(tmp) / n for n in ("p.html", "pairs.json", "zh.json", "out.json"))
            html.write_text(page('<li data-i18n="old-1">Old</li>', {"old-1": "舊"}), encoding="utf-8")
            pairs.write_text(json.dumps([['<li data-i18n="old-1">Old</li>', "<li>Fresh</li>"]]), encoding="utf-8")
            zh.write_text(json.dumps({"fresh-4": "新鮮"}, ensure_ascii=False), encoding="utf-8")
            amend.main(["edit", str(html), str(pairs)])
            self.assertIn("<li>Fresh</li>", html.read_text(encoding="utf-8"))
            amend.main(["merge", str(html), str(zh), str(out)])
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"fresh-4": "新鮮"})
            with self.assertRaises(SystemExit):
                amend.main(["bogus", str(html)])


class InlineReaderTests(unittest.TestCase):
    LINKS = ('<link href="../assets/reader.css" rel="stylesheet"/>\n'
             '<script defer="" src="../assets/reader.js"></script>')

    def test_inlines_both_files_in_any_attribute_order(self):
        for links in (self.LINKS, '<link rel="stylesheet" href="../assets/reader.css">\n'
                                  '<script defer src="../assets/reader.js"></script>'):
            out = inline_reader.inline(links, ".a{b:c}", "go();")
            self.assertNotIn("assets/reader", out)
            self.assertIn("<style>\n.a{b:c}\n</style>", out)
            self.assertIn("DOMContentLoaded", out)
            self.assertIn("go();", out)

    def test_css_with_backslashes_is_copied_verbatim(self):
        out = inline_reader.inline(self.LINKS, r'.q::before{content:"\201C"}', "x();")
        self.assertIn(r'"\201C"', out)

    def test_a_page_without_the_reader_or_with_two_is_refused(self):
        with self.assertRaises(SystemExit):
            inline_reader.inline("<p>no reader</p>", "", "")
        with self.assertRaises(SystemExit):
            inline_reader.inline(self.LINKS + self.LINKS, "", "")


class LinkedRunTests(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(linked_run, "relink_folder_links")  # the tree here is no git checkout
        patch.start()
        self.addCleanup(patch.stop)

    def test_runtime_is_moved_aside_linked_and_restored_even_when_the_command_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            own = tree / linked_run.probe.RUNTIME_DIRS[0]
            own.mkdir(parents=True)
            (own / "stale.txt").write_text("worktree's own", encoding="utf-8")
            seen = {}

            def link(t):
                seen["aside"] = own.with_name(own.name + linked_run.ASIDE).is_dir()
                seen["own_gone"] = not own.exists()
                return ["Harness/x"]

            with mock.patch.object(linked_run.probe, "link_clones", side_effect=link), \
                    mock.patch.object(linked_run.probe, "unlink_clones") as unlink:
                code, output = linked_run.run(tree, [sys.executable, "-c", "print('table'); raise SystemExit(3)"])
            self.assertEqual(code, 3)
            self.assertIn("table", output)
            self.assertEqual(seen, {"aside": True, "own_gone": True})
            unlink.assert_called_once_with(tree, ["Harness/x"])
            self.assertEqual((own / "stale.txt").read_text(encoding="utf-8"), "worktree's own")
            self.assertFalse(own.with_name(own.name + linked_run.ASIDE).exists())

    def test_restores_when_linking_itself_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            own = tree / linked_run.probe.RUNTIME_DIRS[0]
            own.mkdir(parents=True)
            with mock.patch.object(linked_run.probe, "link_clones", side_effect=OSError("no junction")), \
                    mock.patch.object(linked_run.probe, "unlink_clones"):
                with self.assertRaises(OSError):
                    linked_run.run(tree, [sys.executable, "-c", "pass"])
            self.assertTrue(own.is_dir())


class LinkedRunMainCheckoutTests(unittest.TestCase):
    """linked_run against a real main checkout and worktree, with nothing mocked."""

    INDEX = ".claude/hooks/library/index.json"

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.main = Path(folder.name) / "main"
        self.main.mkdir()
        (self.main / ".gitignore").write_text("/.claude/hooks/library/\n/Harness/\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base"]):
            linked_run.probe.git(*args, cwd=self.main)
        (self.main / "Harness" / "shared" / "skill").mkdir(parents=True)
        (self.main / "Harness" / ".runtime").mkdir()
        (self.main / "Harness" / "repos.txt").write_text("Harness/shared\turl\tpin\n", encoding="utf-8")
        self.main_index = self.main / self.INDEX
        self.main_index.parent.mkdir(parents=True)
        self.main_index.write_text("main", encoding="utf-8")
        self.tree = Path(folder.name) / "tree"
        linked_run.probe.git("worktree", "add", "-q", "--detach", str(self.tree), cwd=self.main)
        patch = mock.patch.object(linked_run.probe, "ROOT", self.tree)
        patch.start()
        self.addCleanup(patch.stop)

    def refresh(self):
        """Stand-in for library refresh: report the index it was given, then overwrite it."""
        script = ("from pathlib import Path; p = Path({!r}); print('saw', p.read_text()); "
                  "p.write_text('refreshed')").format(self.INDEX)
        return linked_run.run(self.tree, [sys.executable, "-c", script])

    def test_a_refresh_through_linked_run_never_writes_the_main_index(self):
        own = self.tree / self.INDEX
        own.parent.mkdir(parents=True)
        own.write_text("tree-own", encoding="utf-8")
        code, output = self.refresh()
        self.assertEqual(code, 0, output)
        self.assertIn("saw main", output)  # seeded from main, so the run sees current state
        self.assertEqual(self.main_index.read_text(encoding="utf-8"), "main")
        self.assertEqual(own.read_text(encoding="utf-8"), "tree-own")
        self.assertEqual(sorted(p.name for p in own.parent.iterdir()), ["index.json"])

    def test_a_seeded_index_is_removed_when_the_worktree_had_none(self):
        code, output = self.refresh()
        self.assertEqual(code, 0, output)
        self.assertEqual(self.main_index.read_text(encoding="utf-8"), "main")
        self.assertFalse((self.tree / self.INDEX).exists())

    @unittest.skipUnless(os.name == "nt", "only Windows has file and folder symlinks")
    def test_a_file_link_to_a_folder_becomes_a_folder_link(self):
        link = self.tree / ".claude" / "skills" / "skill"
        link.parent.mkdir(parents=True)
        try:  # how Git for Windows checks out a link whose target does not exist yet
            os.symlink(os.path.join("..", "..", "Harness", "shared", "skill"), link)
        except OSError as error:
            self.skipTest("cannot make symlinks here: {}".format(error))
        linked_run.probe.git("add", str(link), cwd=self.tree)
        code, output = linked_run.run(self.tree, [sys.executable, "-c", "pass"])
        self.assertEqual(code, 0, output)
        self.assertTrue(os.lstat(link).st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY)
        self.assertEqual(linked_run.probe.git("status", "--porcelain", cwd=self.tree), "A  .claude/skills/skill\n")


if __name__ == "__main__":
    unittest.main()
