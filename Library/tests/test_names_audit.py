"""names-audit fails on any name of the old workspace outside the history files.

Each test builds a small git repository, plants one file, and runs
Library/names-audit.py against it. The audit reads only tracked files, so
every planted file is added to the index. Size units such as '64 KB' are not
names and must pass.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "Library" / "names-audit.py"


def audit(files, untracked=()):
    """Run the audit on a fresh repository holding these files; return (code, output)."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=60)
        for rel, text in {**files, **dict(untracked)}.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8") if isinstance(text, str) else text)
        if files:
            subprocess.run(["git", "-C", str(repo), "add", "--", *files], check=True, timeout=60)
        result = subprocess.run([sys.executable, str(AUDIT), str(repo)],
                                capture_output=True, text=True, timeout=120)
        return result.returncode, result.stdout + result.stderr


class Fails(unittest.TestCase):
    def assertFails(self, text, where="notes/a.md:2"):
        code, output = audit({"notes/a.md": "fine\n" + text + "\n"})
        self.assertEqual(code, 1, output)
        self.assertIn(where, output)

    def test_a_planted_old_command_name_fails_with_its_line(self):
        self.assertFails("run kb-check first")

    def test_an_underscore_prefix_fails(self):
        self.assertFails("KB_ROOT=1")
        self.assertFails("def kb_root(): pass")

    def test_the_word_as_a_name_fails(self):
        self.assertFails("Copy it into KB.")
        self.assertFails("kb = Path(__file__)")

    def test_a_library_collection_id_fails(self):
        self.assertFails('"kb:skill:understand"')

    def test_a_harness_patch_adding_an_old_command_still_fails(self):
        name = "Setup/harness-steps/2026-10-21-example/inv.diff"
        for command in ("run kb-check", "++kb-check", "++ kb-check"):
            with self.subTest(command=command):
                patch = "--- a/a.md\n+++ b/a.md\n@@ -1 +1 @@\n-old\n+" + command + "\n"
                code, output = audit({name: patch})
                self.assertEqual(code, 1, output)
                self.assertIn(name + ":5:", output)

    def test_a_harness_document_still_fails_on_an_old_name(self):
        name = "Setup/harness-steps/2026-10-21-example/STEP.md"
        code, output = audit({name: "Use kb-check\n"})
        self.assertEqual(code, 1, output)
        self.assertIn(name + ":1:", output)

    def test_an_old_name_in_a_file_name_fails(self):
        code, output = audit({"setup/kb-library.md": "clean\n"})
        self.assertEqual(code, 1, output)
        self.assertIn("setup/kb-library.md:0", output)

    def test_the_old_start_check_name_fails_in_any_case(self):
        self.assertFails("see RBR/INSTALL.md")
        self.assertFails(".claude/rbr/sync.sh")
        self.assertFails("Rbr banner")
        self.assertFails("Read Before Run is active")


class Passes(unittest.TestCase):
    def assertPasses(self, files, untracked=()):
        code, output = audit(files, untracked)
        self.assertEqual(code, 0, output)

    def test_a_size_unit_passes(self):
        self.assertPasses({"a.md": "64 KB of RAM, a 1.5 KB page, 47KB, 2 kb\n"})

    def test_history_files_are_exempt(self):
        self.assertPasses({
            "CHANGES.md": "kb-check was renamed\n",
            "LESSONS.md": "KB learned this\n",
            "Setup/AGENT_LEDGER.md": "RBR wave\n",
            "Setup/superpowers/specs/x.md": "Read Before Run\n",
            "Library/laya-eval/cases.jsonl": '{"text": "kb-update"}\n',
        })

    def test_a_harness_patch_preserves_historical_context_and_removals(self):
        self.assertPasses({
            "Setup/harness-steps/2026-10-21-example/inv.diff":
            "diff --git a/a.md b/a.md\n--- a/a.md\n+++ b/a.md\n"
            "@@ -1,2 +1,2 @@ old KB\n KB context\n-run kb-check\n+run dev-check\n"
            "diff --git a/KB.md b/KB.md\n--- a/KB.md\n+++ b/KB.md\n"
            "@@ -1 +1 @@\n-run kb-check\n+run dev-check\n",
        })

    def test_an_untracked_file_is_not_read(self):
        self.assertPasses({"a.md": "clean\n"}, untracked={"b.md": "kb-check\n"})

    def test_a_binary_file_is_skipped(self):
        self.assertPasses({"logo.png": b"\x89PNG\x00kb-check\x00"})

    def test_ordinary_words_pass(self):
        self.assertPasses({"a.py": "keyboard = kbd = 'mkb-x'\nrbac = 'herb'\n"})

    def test_a_hash_that_happens_to_spell_it_passes(self):
        # package-lock.json integrity values are base64; one holds "...WGCmRbrml...".
        self.assertPasses({"lock.json": '"integrity": "sha512-svtcWGCmRbrml64SPw/jJD4G=="\n'})


if __name__ == "__main__":
    unittest.main()
