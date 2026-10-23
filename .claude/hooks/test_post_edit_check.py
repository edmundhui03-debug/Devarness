#!/usr/bin/env python3
"""Tests for post_edit_check.py, the PostToolUse hook that runs the house checker on an edited file.

The hook never blocks: the edit has already happened. It prints the checker's
findings back into the session as additionalContext, only for files dev owns,
and stays silent on everything else. Each test builds a stand-in dev with the
real checkers copied in, because md-format decides "ours" by walking up to a folder
holding CLAUDE.md and .claude/.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import runpy
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HOOK = HERE / "post_edit_check.py"
I18N_PYTHON = Path.home() / ".local" / "share" / "uv" / "tools" / "markitdown" / "bin" / "python"

GOOD_MD = """# The heading states a claim

> **2026-09-18** · Peter · `current`
>
> A short summary of two sentences. It says what the document concludes.

## The one section states its claim too

`fixed` · nothing left to do

Prose wrapped well inside eighty columns, with the evidence at `path:1`.
"""
BAD_MD = "# a title\n\nno header block, no summary, nothing the format asks for\n"


class HookTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="post-edit-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "dev copy"
        for relative in (".claude/hooks", "Harness/bin", "Harness/templates"):
            (self.root / relative).mkdir(parents=True)
        (self.root / "CLAUDE.md").write_text("# router\n", encoding="utf-8")
        for name in ("md-format", "i18n"):
            shutil.copy2(str(ROOT / "Harness" / "bin" / name), str(self.root / "Harness" / "bin" / name))
        for name in ("repos.txt", "separate-projects.txt"):
            shutil.copy2(str(ROOT / "Harness" / name), str(self.root / "Harness" / name))
        shutil.copy2(str(HOOK), str(self.root / ".claude" / "hooks" / HOOK.name))
        self.hook = self.root / ".claude" / "hooks" / HOOK.name
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull,
                        PYTHONIOENCODING="utf-8")
        self.git("init", "-q")
        (self.root / ".gitignore").write_text("/ignored/\n", encoding="utf-8")

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.root), *args], env=self.env, check=True,
                              capture_output=True, text=True)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def fire(self, path, tool="Edit", event="PostToolUse", raw=None):
        payload = raw if raw is not None else json.dumps(
            {"hook_event_name": event, "tool_name": tool, "cwd": str(self.root),
             "tool_input": {"file_path": str(path)}, "tool_response": {}})
        return subprocess.run([sys.executable, str(self.hook)], input=payload, env=self.env,
                              capture_output=True, text=True, timeout=120)

    def context(self, done):
        self.assertEqual(done.returncode, 0, done.stderr)
        if not done.stdout.strip():
            return None
        data = json.loads(done.stdout)
        return data["hookSpecificOutput"]["additionalContext"]

    def test_a_markdown_file_that_breaks_the_house_format_is_reported_back(self):
        path = self.write("Setup/note.md", BAD_MD)
        text = self.context(self.fire(path))
        self.assertIsNotNone(text, "the hook stayed silent on a bad page")
        self.assertIn("md-format check", text)
        self.assertIn("note.md", text)
        self.assertRegex(text, r"E\d\d\d")

    def test_a_clean_markdown_file_produces_no_output_at_all(self):
        path = self.write("Setup/good.md", GOOD_MD)
        done = self.fire(path)
        self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)

    def test_a_write_is_checked_like_an_edit(self):
        path = self.write("Setup/new.md", BAD_MD)
        self.assertIsNotNone(self.context(self.fire(path, tool="Write")))

    def test_files_dev_does_not_own_are_left_alone(self):
        cases = {
            "ignored": self.write("ignored/note.md", BAD_MD),
            "nested repository": self.write("nested/note.md", BAD_MD),
            "template": self.write("Harness/templates/markdown-doc.md", BAD_MD),
            "outside the root": Path(self.root.parent, "elsewhere.md"),
        }
        cases["outside the root"].write_text(BAD_MD, encoding="utf-8")
        self.git("init", "-q", cwd=self.root / "nested")
        for label, path in cases.items():
            with self.subTest(label):
                done = self.fire(path)
                self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)

    def test_other_tools_other_events_and_other_file_types_are_ignored(self):
        path = self.write("Setup/note.md", BAD_MD)
        for label, kwargs in (("a Bash call", {"tool": "Bash"}), ("a PreToolUse event", {"event": "PreToolUse"})):
            with self.subTest(label):
                done = self.fire(path, **kwargs)
                self.assertEqual((done.returncode, done.stdout), (0, ""))
        py = self.write("Setup/script.py", "print('not a document')\n")
        done = self.fire(py)
        self.assertEqual((done.returncode, done.stdout), (0, ""), "with no tieitup command, code is not checked")
        txt = self.write("Setup/data.txt", "not code\n")
        done = self.fire(txt)
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_a_checker_that_cannot_run_says_nothing_about_the_document(self):
        # i18n on a device with no markitdown python prints "needs markitdown's
        # python at ..." and exits nonzero; without this it answered every HTML edit
        # on a fresh machine with a complaint about the machine.
        broken = self.root / "Harness" / "bin" / "md-format"
        broken.write_text("#!/usr/bin/env python3\n"
                          "import sys\n"
                          "print('md-format: needs something this device does not have', file=sys.stderr)\n"
                          "sys.exit(1)\n", encoding="utf-8")
        done = self.fire(self.write("Setup/note.md", BAD_MD))
        self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)

    def test_input_it_cannot_read_never_fails_the_edit(self):
        for raw in ("", "not json", json.dumps({"tool_name": "Edit"}), json.dumps({"tool_name": "Edit", "tool_input": {}})):
            with self.subTest(raw[:12]):
                done = self.fire(None, raw=raw)
                self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_a_long_report_is_cut_and_says_how_much_was_cut(self):
        # a valid header, then forty lines each over eighty columns: md-format stops at
        # a missing header, so the fixture must get past that to be long
        body = "\n".join("a line of prose that runs on far past the eightieth column of the page, number %d" % i
                         for i in range(40))
        path = self.write("Setup/long.md", GOOD_MD + "\n" + body + "\n")
        text = self.context(self.fire(path))
        self.assertIsNotNone(text)
        self.assertLessEqual(len(text.splitlines()), 16)
        self.assertIn("more", text)

    @unittest.skipUnless(I18N_PYTHON.exists(), "i18n needs markitdown's python")
    def test_an_html_page_without_the_toggle_is_reported_back(self):
        path = self.write("Setup/page.html", "<!doctype html><html><head><title>Page</title></head>"
                          "<body><h1>Only English</h1><p>No toggle, no dictionary.</p></body></html>\n")
        text = self.context(self.fire(path))
        self.assertIsNotNone(text, "the hook stayed silent on a page with no toggle")
        self.assertIn("i18n check", text)


# A stand-in for tieitup: one finding naming the file and the folder it ran in, or
# nothing when the file says "clean"; a fault goes to stderr and still exits 0.
STUB = """#!/usr/bin/env python3
import os, sys
path = sys.argv[-1]
text = open(path, encoding="utf-8").read()
if "fault" in text:
    print("tieitup: cannot read the range", file=sys.stderr)
elif "clean" not in text:
    print("%s:1 [stub 0000abcd] a finding (rule 1; ran in %s)" % (os.path.basename(path), os.path.basename(os.getcwd())))
"""


class CodeCheckTests(unittest.TestCase):
    """Code files go to tieitup check, and any line it prints on stdout is a finding."""
    git, write, fire, context = HookTests.git, HookTests.write, HookTests.fire, HookTests.context

    def setUp(self):
        HookTests.setUp(self)
        (self.root / "Harness/bin/tieitup").write_text(STUB, encoding="utf-8")

    def test_a_finding_in_a_code_file_is_reported_back(self):
        for name in ("Setup/tool.py", "Setup/run.sh", "Setup/fw.c", "Setup/fw.h", "Setup/page.ts", "Setup/app.jsx"):
            with self.subTest(name):
                text = self.context(self.fire(self.write(name, "x = 1\n")))
                self.assertIsNotNone(text)
                self.assertIn("tieitup check", text)
                self.assertIn("[stub 0000abcd]", text)

    def test_a_clean_file_says_nothing(self):
        done = self.fire(self.write("Setup/tool.py", "clean\n"))
        self.assertEqual((done.returncode, done.stdout), (0, ""), done.stderr)

    def test_a_checker_fault_is_unverified_and_never_blocks_the_edit(self):
        done = self.fire(self.write("Setup/tool.py", "fault\n"))
        self.assertEqual(done.returncode, 0)
        text = self.context(done)
        self.assertIsNotNone(text)
        self.assertIn("UNVERIFIED", text)
        self.assertNotIn("a finding", text)

    def test_a_nonzero_checker_exit_is_unverified(self):
        (self.root / "Harness/bin/tieitup").write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
        done = self.fire(self.write("Setup/tool.py", "x = 1\n"))
        self.assertEqual(done.returncode, 0)
        self.assertIn("exit 2", self.context(done))

    def test_checker_timeout_or_launch_failure_is_unverified(self):
        report = runpy.run_path(str(HOOK))["code_report"]
        failures = (subprocess.TimeoutExpired(["checker"], 25), OSError("cannot start"))
        for error in failures:
            with self.subTest(error=type(error).__name__), mock.patch.object(subprocess, "run", side_effect=error):
                self.assertIn("UNVERIFIED", report(Path("tool.py"), self.root))

    def test_stderr_does_not_hide_findings_or_copy_diagnostics_into_context(self):
        report = runpy.run_path(str(HOOK))["code_report"]
        done = subprocess.CompletedProcess([], 0, "tool.py:1 [stub] a finding\n", "private diagnostic")
        with mock.patch.object(subprocess, "run", return_value=done):
            text = report(Path("tool.py"), self.root)
        self.assertIn("UNVERIFIED", text)
        self.assertIn("[stub] a finding", text)
        self.assertNotIn("private diagnostic", text)

    def test_an_extensionless_script_is_checked_by_its_shebang(self):
        self.assertIsNotNone(self.context(self.fire(self.write("Harness/bin/tool", "#!/usr/bin/env python3\nx = 1\n"))))
        self.assertIsNotNone(self.context(self.fire(self.write("Harness/bin/job", "#!/bin/bash\nx=1\n"))))
        done = self.fire(self.write("Setup/notes", "plain text with no shebang\n"))
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_code_in_a_separate_project_is_checked_in_that_repository(self):
        project = self.root / "Projects/WORK/EXAMPLE001_example-terminal"
        (self.root / "Harness/separate-projects.txt").write_text(
            "Projects/WORK/EXAMPLE001_example-terminal\n", encoding="utf-8")
        project.mkdir(parents=True)
        self.git("init", "-q", cwd=project)
        text = self.context(self.fire(self.write("Projects/WORK/EXAMPLE001_example-terminal/src/main.ts", "x = 1\n")))
        self.assertIsNotNone(text)
        self.assertIn("ran in EXAMPLE001_example-terminal", text)
        done = self.fire(self.write("Projects/WORK/EXAMPLE001_example-terminal/notes.md", BAD_MD))
        self.assertEqual((done.returncode, done.stdout), (0, ""), "a separate project's documents stay its own")

    def test_code_in_an_unlisted_nested_repository_is_left_alone(self):
        self.git("init", "-q", cwd=self.write("nested/keep", "").parent)
        done = self.fire(self.write("nested/main.py", "x = 1\n"))
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_no_command_means_no_check(self):
        (self.root / "Harness/bin/tieitup").unlink()
        done = self.fire(self.write("Setup/tool.py", "x = 1\n"))
        self.assertEqual((done.returncode, done.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
