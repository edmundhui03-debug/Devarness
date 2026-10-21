#!/usr/bin/env python3
"""dashboard export: the snapshot the developer's dashboard reads, on a temporary workspace.

Run it with python3 from anywhere; it finds the tool in the launcher folder
beside its own. Design: Library/dashboard/DESIGN.md, whose "Three formats join
the parts" fixes the format: the page and AGENTS.md are written against it.

Each test builds a small workspace with its own copy of md-format and the
dashboard exporter, so the open work and the library are the fixture's, never
this checkout's.
"""
import argparse
import errno
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

TOOL = Path(__file__).resolve().parents[1] / "bin" / "dashboard"
MD_FORMAT = TOOL.with_name("md-format")
ROOT = TOOL.parents[2]
SNAPSHOT = Path("Library") / "dashboard" / "snapshot.json"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
KEEP = ("PATH", "SYSTEMROOT", "USERPROFILE", "HOME", "TEMP", "TMP")


def small_env():
    """A small environment of its own for each child, never the whole one (LESSONS.md:460)."""
    return {key: os.environ[key] for key in KEEP if key in os.environ}


DOC = """# {title}

> **2026-10-09** · Peter · `current`
>
> One sentence. Another sentence.
{sections}"""

SECTION = """
## {heading}

`{status}`

Prose.
"""


def document(title, *sections):
    return DOC.format(title=title, sections="".join(
        SECTION.format(heading=heading, status=status) for heading, status in sections))


ENTRY_FIELDS = ("name", "kind", "collection", "summary", "path")


def library_entry(number, purpose="Find a thing."):
    return {"id": "dev:skill:tool-%04d" % number, "name": "tool-%04d" % number, "kind": "skill",
            "collection": "dev", "purpose": purpose, "category": "tools",
            "path": ".claude/skills/tool-%04d/SKILL.md" % number, "owner_ref": "x", "owner": None,
            "scope": ".", "mode": "library-only", "aliases": [], "exclusions": [],
            "source_present": True, "configured_clients": [], "runtime_status": "unknown",
            "unfinished": False}


class TempWorkspace:
    """A workspace with marked documents in each project, one outside them, and a library index."""

    def __init__(self, base):
        self.root = base / "dev with spaces"
        (self.root / ".claude").mkdir(parents=True)
        (self.root / "CLAUDE.md").write_text("", encoding="utf-8")      # how md-format finds its root
        self.tool = self.root / TOOL.relative_to(ROOT)
        self.tool.parent.mkdir(parents=True)
        self.tool.write_bytes(TOOL.read_bytes())
        self.tool.with_name("md-format").write_bytes(MD_FORMAT.read_bytes())
        subprocess.run(["git", "init", "-q", str(self.root)], capture_output=True, check=True,
                       env=small_env(), creationflags=NO_WINDOW)
        self.write("PCB Tools/AGENTS/board.md", document(
            "The board waits on two things",
            ("The footprint is undecided", "needs-owner"),
            ("The netlist is clean", "fixed"),
            ("Routing is half done", "open")))
        self.write("DATASET/run.md", document("The run is stopped", ("The mesh is too coarse", "blocked")))
        self.write("Research/paper.md", document("The paper is drafted", ("Results are partly in", "partial")))
        self.write("Setup/elsewhere.md", document("Not a project", ("Outside every project", "open")))
        self.write("Library/dashboard/DESIGN.md", document("The dashboard", ("The dashboard's own work", "open")))
        # The library index sits in a library folder beside the session hooks.
        self.index = self.root / ".claude" / "hooks" / "library" / "index.json"
        self.write_index([library_entry(1, "Find a thing.\nOn two lines."), library_entry(2)])

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        subprocess.run(["git", "-C", str(self.root), "add", rel], capture_output=True, check=True,
                       env=small_env(), creationflags=NO_WINDOW)

    def write_index(self, entries):
        self.index.parent.mkdir(parents=True, exist_ok=True)
        self.index.write_text(json.dumps({"schema": 1, "fingerprints": {}, "diagnostics": [],
                                          "entries": entries}), encoding="utf-8")

    def export(self, *extra):
        done = subprocess.run([sys.executable, str(self.tool), "export", *extra], capture_output=True,
                              text=True, encoding="utf-8", timeout=120, cwd=str(self.root.parent),
                              env=dict(small_env(), PYTHONIOENCODING="utf-8"), creationflags=NO_WINDOW)
        if done.returncode:
            raise AssertionError("dashboard export failed: " + done.stdout + done.stderr)
        return done

    def snapshot(self, path=None):
        return json.loads((path or self.root / SNAPSHOT).read_text(encoding="utf-8"))


class ExportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="dashboard-")
        self.addCleanup(temp.cleanup)
        self.ws = TempWorkspace(Path(temp.name))

    def test_the_snapshot_has_the_agreed_shape(self):
        self.ws.export("--quiet")
        data = self.ws.snapshot()
        self.assertEqual(set(data), {"version", "generated_at", "projects", "library"})
        self.assertEqual(data["version"], 1)
        self.assertRegex(data["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        self.assertEqual(set(data["projects"]), {"PCB", "DATASET", "Research"})
        self.assertEqual(set(data["library"]), {"count", "entries"})

    def test_each_project_lists_its_live_sections_and_nothing_else(self):
        self.ws.export("--quiet")
        projects = self.ws.snapshot()["projects"]
        # Most urgent first, in md-format's own order: blocked, needs-owner, open, partial.
        self.assertEqual(projects["PCB"], [
            {"title": "The footprint is undecided", "status": "needs-owner",
             "file": "PCB Tools/AGENTS/board.md", "line": 9},
            {"title": "Routing is half done", "status": "open",
             "file": "PCB Tools/AGENTS/board.md", "line": 21}])
        self.assertEqual([(i["title"], i["status"]) for i in projects["DATASET"]],
                         [("The mesh is too coarse", "blocked")])
        self.assertEqual([(i["title"], i["status"]) for i in projects["Research"]],
                         [("Results are partly in", "partial")])
        listed = json.dumps(projects)
        self.assertNotIn("Outside every project", listed)
        self.assertNotIn("The dashboard's own work", listed)

    def test_a_project_also_takes_its_folder_under_projects(self):
        self.ws.write("Projects/PCB/sensor.md", document("The sensor board", ("Pick the regulator", "open")))
        self.ws.write("Projects/Research/notes.md", document("Notes", ("Read the paper", "partial")))
        self.ws.export("--quiet")
        projects = self.ws.snapshot()["projects"]
        self.assertIn(("Pick the regulator", "Projects/PCB/sensor.md"),
                      [(i["title"], i["file"]) for i in projects["PCB"]])
        self.assertIn(("Read the paper", "Projects/Research/notes.md"),
                      [(i["title"], i["file"]) for i in projects["Research"]])

    def test_the_library_gives_five_fields_and_a_one_line_summary(self):
        self.ws.export("--quiet")
        library = self.ws.snapshot()["library"]
        self.assertEqual(library["count"], 2)
        first = library["entries"][0]
        self.assertEqual(tuple(sorted(first)), tuple(sorted(ENTRY_FIELDS)))
        self.assertEqual(first, {"name": "tool-0001", "kind": "skill", "collection": "dev",
                                 "summary": "Find a thing. On two lines.",
                                 "path": ".claude/skills/tool-0001/SKILL.md"})

    def test_a_library_path_never_names_this_machine(self):
        # The real index holds plugin caches by absolute path under the user's
        # home; the snapshot is read in a browser and must not carry either.
        home = Path.home()
        inside, cached, other, top = (library_entry(n) for n in (1, 2, 3, 5))
        inside["path"] = str(self.ws.root.resolve() / ".claude" / "skills" / "tool-0001" / "SKILL.md")
        cached["path"] = (home / ".claude" / "plugins" / "cache" / "tool-0002" / "SKILL.md").as_posix()
        other["path"] = str(Path(home.anchor) / "Elsewhere" / "tool-0003" / "SKILL.md")
        top["path"] = str(Path(home.anchor) / "SKILL.md")
        self.ws.write_index([inside, cached, other, library_entry(4), top])
        self.ws.export("--quiet")
        paths = [e["path"] for e in self.ws.snapshot()["library"]["entries"]]
        self.assertEqual(paths, [".claude/skills/tool-0001/SKILL.md",
                                 "~/.claude/plugins/cache/tool-0002/SKILL.md",
                                 "…/tool-0003/SKILL.md",
                                 ".claude/skills/tool-0004/SKILL.md",
                                 "…/SKILL.md"])
        text = (self.ws.root / SNAPSHOT).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", text), text)
        for spelled in (str(home), home.as_posix()):
            self.assertNotIn(spelled, text)
        self.assertNotIn(home.name, [part for p in paths for part in p.split("/")])

    def test_a_long_purpose_is_cut_to_one_short_line(self):
        self.ws.write_index([library_entry(1, "word " * 200)])
        self.ws.export("--quiet")
        summary = self.ws.snapshot()["library"]["entries"][0]["summary"]
        self.assertLessEqual(len(summary), 160)
        self.assertTrue(summary.endswith("…"), summary)

    def test_the_library_is_capped_at_1000_entries_and_counts_them_all(self):
        self.ws.write_index([library_entry(n) for n in range(1005)])
        self.ws.export("--quiet")
        library = self.ws.snapshot()["library"]
        self.assertEqual((library["count"], len(library["entries"])), (1005, 1000))

    def test_out_writes_there_only_and_quiet_prints_nothing(self):
        out = self.ws.root.parent / "elsewhere" / "snap.json"
        done = self.ws.export("--out", str(out), "--quiet")
        self.assertEqual(done.stdout, "")
        self.assertEqual(self.ws.snapshot(out)["version"], 1)
        self.assertFalse((self.ws.root / SNAPSHOT).exists())

    def test_a_plain_export_says_what_it_wrote(self):
        done = self.ws.export()
        self.assertIn("Library/dashboard/snapshot.json", done.stdout)
        self.assertRegex(done.stdout, r"PCB 2, DATASET 1, Research 1")
        self.assertIn("library 2 entries", done.stdout)

    def test_a_second_export_replaces_the_first_and_leaves_no_scratch_file(self):
        self.ws.export("--quiet")
        self.ws.write("DATASET/later.md", document("Later", ("A second block", "blocked")))
        self.ws.export("--quiet")
        self.assertEqual(len(self.ws.snapshot()["projects"]["DATASET"]), 2)
        self.assertEqual(sorted(p.name for p in (self.ws.root / SNAPSHOT).parent.iterdir()),
                         ["DESIGN.md", "snapshot.json"])

    def test_a_missing_library_index_gives_an_empty_library_and_a_note(self):
        self.ws.index.unlink()
        self.ws.export("--quiet")
        data = self.ws.snapshot()
        self.assertEqual(data["library"], {"count": 0, "entries": []})
        self.assertIn("library", data["note"])
        self.assertEqual(len(data["projects"]["PCB"]), 2)        # the rest is still there

    def test_unreadable_inputs_give_empty_lists_and_a_note_never_a_crash(self):
        for junk in ("", "not json", "[]", '{"entries": 7}', '{"entries": [3, "x"]}'):
            with self.subTest(index=junk):
                self.ws.index.write_text(junk, encoding="utf-8")
                self.ws.export("--quiet")
                data = self.ws.snapshot()
                self.assertEqual(data["library"]["entries"], [])
                self.assertIn("note", data)
        # md-format replaced by one that prints no index at all.
        self.ws.tool.with_name("md-format").write_text("print('not an index')\n", encoding="utf-8")
        self.ws.export("--quiet")
        data = self.ws.snapshot()
        self.assertEqual(data["projects"], {"PCB": [], "DATASET": [], "Research": []})
        self.assertIn("md-format", data["note"])


class InsideTests(unittest.TestCase):
    """The parts a run from outside cannot see: the window md-format gets, and the atomic write."""

    def setUp(self):
        self.tool = runpy.run_path(str(TOOL))["main"].__globals__

    def test_md_format_runs_beside_it_under_this_python_without_a_window(self):
        calls = []

        def spy(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout='{"sections": []}', stderr="")
        with mock.patch.object(subprocess, "run", spy):
            self.tool["projects"]()
        argv, kwargs = calls[0]
        self.assertEqual(argv[:2], [sys.executable, str(MD_FORMAT)])
        self.assertEqual(argv[2:], ["status", "--json"])
        self.assertEqual(kwargs.get("creationflags"), getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertLessEqual(kwargs.get("timeout"), 60)

    def test_a_failed_write_leaves_the_last_snapshot_whole(self):
        with tempfile.TemporaryDirectory(prefix="dashboard-atomic-") as tmp:
            path = Path(tmp) / "snapshot.json"
            self.tool["write_atomic"](path, {"version": 1})
            before = path.read_bytes()
            with self.assertRaises(TypeError):
                self.tool["write_atomic"](path, {"version": 1, "broken": object()})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["snapshot.json"])
            self.assertNotIn(b"\r\n", before)

    def test_serve_names_its_python_for_the_tasks_page(self):
        seen = {}

        def call(cmd, cwd=None, env=None):
            seen["python"] = (env or {}).get("DEVARNESS_PYTHON")
            return 0

        with mock.patch.object(self.tool["subprocess"], "call", call), \
                mock.patch.object(self.tool["shutil"], "which", lambda name: "node"):
            self.tool["serve"](argparse.Namespace(port=47900, allow_origin=[]))
        self.assertEqual(seen["python"], sys.executable)

    def test_the_tool_never_spells_the_old_folder_name(self):
        # A folder rename is pending; paths are derived from the tool's own place.
        old = "".join(chr(c) for c in (82, 66, 82))
        self.assertIsNone(re.search(old, TOOL.read_text(encoding="utf-8"), re.I))


class WaitTests(unittest.TestCase):
    """dashboard wait: an agent's way to carry on once the owner answers."""

    def mailbox(self, status="open", answer=""):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "questions.json"
        question = {"id": "q-1", "project": "Library", "task": "t", "asked_by": "Peter",
                    "asked_at": "2026-10-09T10:00:00+08:00", "question": "Port?", "status": status,
                    "answer": answer, "answered_at": "", "used_by": "", "used_at": "", "used_note": ""}
        path.write_text(json.dumps({"version": 1, "questions": [question]}, indent=2) + "\n", encoding="utf-8")
        return path

    def wait(self, path, *args):
        return subprocess.run([sys.executable, str(TOOL), "wait", *args, "--questions", str(path)],
                              capture_output=True, text=True, encoding="utf-8", timeout=30, env=small_env(),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_an_answered_question_prints_its_answer(self):
        done = self.wait(self.mailbox("answered", "Use 47900"), "q-1")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "Use 47900"))

    def test_it_waits_until_the_owner_answers(self):
        path = self.mailbox()
        proc = subprocess.Popen([sys.executable, str(TOOL), "wait", "q-1", "--questions", str(path), "--interval", "0.1"],
                                stdout=subprocess.PIPE, text=True, encoding="utf-8", env=small_env(),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.addCleanup(proc.kill)
        time.sleep(0.5)
        self.assertIsNone(proc.poll(), "it returned before any answer")
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["questions"][0].update(status="answered", answer="Yes")
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        out, _ = proc.communicate(timeout=10)
        self.assertEqual((proc.returncode, out.strip()), (0, "Yes"))

    def test_an_unknown_id_and_a_timeout_have_their_own_exit_codes(self):
        path = self.mailbox()
        self.assertEqual(self.wait(path, "q-404").returncode, 2)
        self.assertEqual(self.wait(path, "q-1", "--interval", "0.1", "--timeout", "0.3").returncode, 3)

    def test_a_mailbox_saved_with_a_byte_order_mark_still_gives_the_answer(self):
        # PowerShell 5.1 writes UTF-8 with a BOM; the timeout only stops a build without the fix.
        path = self.mailbox("answered", "Use 47900")
        path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8-sig")
        done = self.wait(path, "q-1", "--interval", "0.05", "--timeout", "2")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "Use 47900"), done.stderr)

    def test_a_used_question_still_prints_its_answer(self):
        done = self.wait(self.mailbox("used", "Use 47900"), "q-1")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "Use 47900"))

    def test_a_non_ascii_answer_is_written_as_utf8_whatever_the_console_encoding(self):
        # With UTF-8 mode off and no PYTHONIOENCODING, a piped stdout takes the
        # console code page (cp950 here), which cannot hold the emoji at all.
        answer = "用 47900 👍"
        env = small_env()
        env["PYTHONUTF8"] = "0"
        done = subprocess.run([sys.executable, str(TOOL), "wait", "q-1", "--questions",
                               str(self.mailbox("answered", answer))],
                              capture_output=True, timeout=30, env=env,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.decode("utf-8").strip(), answer)

    def test_the_interval_must_be_positive(self):
        path = self.mailbox()
        for interval in ("0", "-1", "nan"):
            with self.subTest(interval=interval):
                # The timeout only keeps a build without the check from spinning for ever.
                done = self.wait(path, "q-1", "--interval", interval, "--timeout", "0.3")
                self.assertEqual(done.returncode, 2)
                self.assertIn("--interval", done.stderr)

    def test_it_never_sleeps_past_the_deadline(self):
        started = time.monotonic()
        done = self.wait(self.mailbox(), "q-1", "--interval", "20", "--timeout", "0.5")
        self.assertEqual(done.returncode, 3)
        self.assertLess(time.monotonic() - started, 10)

    def test_an_unreadable_file_is_reported_once_and_the_wait_goes_on(self):
        missing = Path(tempfile.gettempdir()) / "dashboard-no-such-dir" / "questions.json"
        done = self.wait(missing, "q-1", "--interval", "0.05", "--timeout", "0.5")
        self.assertEqual(done.returncode, 3)
        lines = [line for line in done.stderr.splitlines() if "cannot read" in line]
        self.assertEqual(len(lines), 1, done.stderr)
        self.assertIn("still waiting", lines[0])

    def test_a_questions_list_that_is_null_is_not_a_crash(self):
        path = self.mailbox()
        path.write_text('{"version": 1, "questions": null}\n', encoding="utf-8")
        done = self.wait(path, "q-1", "--interval", "0.05", "--timeout", "0.3")
        self.assertEqual(done.returncode, 3)
        self.assertNotIn("Traceback", done.stderr)

    def test_ctrl_c_ends_the_wait_with_130_and_no_traceback(self):
        tool = runpy.run_path(str(TOOL))
        args = argparse.Namespace(id="q-1", questions=self.mailbox(), interval=0.1, timeout=0.0)
        out = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        with mock.patch.object(sys, "stdout", out), mock.patch.object(time, "sleep", side_effect=KeyboardInterrupt):
            self.assertEqual(tool["wait"](args), 130)


FIELDS = ["id", "project", "task", "asked_by", "asked_at", "question", "status", "answer",
          "answered_at", "used_by", "used_at", "used_note"]
NODE = shutil.which("node")
QUESTIONS_MJS = TOOL.parents[1] / "dashboard" / "server" / "questions.mjs"
ASK = ("ask", "--project", "PCB", "--task", "t", "--asked-by", "May", "Q?")
BOM = chr(0xFEFF)  # JavaScript's trim() removes it; Python's strip() keeps it


def entry(qid, **extra):
    q = dict.fromkeys(FIELDS, "")
    q.update(id=qid, project="PCB", task="Order", asked_by="Peter", asked_at="2026-10-01T09:00:00+08:00",
             question="Which holder?", status="open")
    q.update(extra)
    return q


class MailboxTests(unittest.TestCase):
    """dashboard ask and dashboard used: the agents' only way to write questions.json."""

    def mailbox(self, *questions):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "questions.json"
        self.save(path, {"version": 1, "questions": list(questions)})
        return path

    @staticmethod
    def save(path, doc):
        # The server's own format: two-space indent, characters as they are, a final newline.
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    def run_tool(self, path, *args, env=None):
        return subprocess.run([sys.executable, str(TOOL), *args, "--questions", str(path)],
                              capture_output=True, text=True, encoding="utf-8", timeout=30,
                              env=env or small_env(), creationflags=NO_WINDOW)

    def ask(self, path, question="Which holder?", project="PCB", asked_by="Peter", task="CO detector order"):
        return self.run_tool(path, "ask", "--project", project, "--task", task, "--asked-by", asked_by, question)

    @staticmethod
    def tool():
        """The command's globals, loaded in this process so a test can patch them."""
        return runpy.run_path(str(TOOL))["main"].__globals__

    @staticmethod
    def call(tool, path, *args):
        """The command run in this process, quietly: its exit code and what it printed to stderr."""
        err = io.StringIO()
        with mock.patch.object(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")), \
                mock.patch.object(sys, "stderr", err):
            return tool["main"]([*args, "--questions", str(path)]), err.getvalue()

    def test_ask_adds_a_well_formed_open_question_with_the_next_free_number(self):
        today = time.strftime("%Y-%m-%d")
        # The number counts per day and project: neither of these is taken into account.
        other_day, other_project = entry("q-2026-10-01-pcb-007"), entry("q-%s-library-004" % today, project="Library")
        path = self.mailbox(other_day, other_project)
        first, second = self.ask(path), self.ask(path, "And the cell?")
        self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr + second.stderr)
        self.assertEqual([first.stdout.strip(), second.stdout.strip()], ["q-%s-pcb-001" % today, "q-%s-pcb-002" % today])
        text = path.read_text(encoding="utf-8")
        questions = json.loads(text)["questions"]
        self.assertEqual(questions[:2], [other_day, other_project])
        added = questions[2]
        self.assertEqual(list(added), FIELDS)
        self.assertRegex(added["asked_at"], r"^%sT\d\d:\d\d:\d\d[+-]\d\d:\d\d$" % today)
        self.assertEqual({k: v for k, v in added.items() if k != "asked_at"}, {
            "id": "q-%s-pcb-001" % today, "project": "PCB", "task": "CO detector order", "asked_by": "Peter",
            "question": "Which holder?", "status": "open", "answer": "", "answered_at": "",
            "used_by": "", "used_at": "", "used_note": ""})
        self.assertEqual(text, json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n")

    def test_ask_refuses_an_unknown_project_and_an_empty_asker_or_question(self):
        path = self.mailbox(entry("q-1"))
        before = path.read_bytes()
        for done, reason in ((self.ask(path, project="SAMPLE_FIRMWARE"), "invalid choice: 'SAMPLE_FIRMWARE'"),
                             (self.ask(path, asked_by=" "), "must not be empty"),
                             (self.ask(path, question="  "), "must not be empty")):
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertIn(reason, done.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_used_changes_only_its_four_fields(self):
        answered = entry("q-1", status="answered", answer="Both sides", answered_at="2026-10-09T12:00:00.000Z")
        other = entry("q-2", answer="", question="用邊款電池座？")
        path = self.mailbox(answered, other)
        done = self.run_tool(path, "used", "q-1", "--by", "Peter", "--note", "Ordered with both sides assembled.")
        self.assertEqual(done.returncode, 0, done.stderr)
        after = json.loads(path.read_text(encoding="utf-8"))["questions"]
        changed = {k for k in FIELDS if after[0][k] != answered[k]}
        self.assertEqual(changed, {"status", "used_by", "used_at", "used_note"})
        self.assertEqual([after[0]["status"], after[0]["used_by"], after[0]["used_note"]],
                         ["used", "Peter", "Ordered with both sides assembled."])
        self.assertRegex(after[0]["used_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        expected = {"version": 1, "questions": [after[0], other]}
        self.assertEqual(path.read_text(encoding="utf-8"), json.dumps(expected, indent=2, ensure_ascii=False) + "\n")

    def test_used_refuses_an_open_a_used_or_an_unknown_question(self):
        path = self.mailbox(entry("q-open"), entry("q-used", status="used", answer="x"))
        before = path.read_bytes()
        for qid in ("q-open", "q-used", "q-404"):
            done = self.run_tool(path, "used", qid, "--by", "Peter", "--note", "Done.")
            self.assertEqual(done.returncode, 2, qid)
            self.assertIn(qid, done.stderr)
        self.assertEqual(path.read_bytes(), before)

    def test_ask_waits_for_a_held_lock_and_goes_on_once_it_is_let_go(self):
        path = self.mailbox(entry("q-1"))
        lock = Path(str(path) + ".lock")
        lock.write_text("999 2026-10-09T12:00:00+08:00", encoding="utf-8")
        before = path.read_bytes()
        proc = subprocess.Popen([sys.executable, str(TOOL), "ask", "--project", "PCB", "--task", "t",
                                 "--asked-by", "May", "Which holder?", "--questions", str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                env=small_env(), creationflags=NO_WINDOW)
        self.addCleanup(proc.kill)
        time.sleep(1)
        self.assertIsNone(proc.poll(), "it wrote while another writer held the lock")
        self.assertEqual(path.read_bytes(), before)
        lock.unlink()
        out, err = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual([q["id"] for q in json.loads(path.read_text(encoding="utf-8"))["questions"]],
                         ["q-1", out.strip()])
        self.assertFalse(lock.exists())

    def test_a_lock_that_never_clears_exits_4_and_a_stale_one_is_broken(self):
        tool = runpy.run_path(str(TOOL))["main"].__globals__
        path = self.mailbox(entry("q-1"))
        lock = Path(str(path) + ".lock")
        lock.write_text("999 still at work", encoding="utf-8")
        before = path.read_bytes()
        argv = ["ask", "--project", "PCB", "--task", "t", "--asked-by", "Aster", "Q?", "--questions", str(path)]
        out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.dict(tool, {"LOCK_WAIT": 0.2}), mock.patch.object(sys, "stdout", out), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(tool["main"](argv), 4)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(lock.read_text(encoding="utf-8"), "999 still at work")
            old = time.time() - 60
            os.utime(str(lock), (old, old))
            self.assertEqual(tool["main"](argv), 0)
        self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["questions"]), 2)
        self.assertFalse(lock.exists())

    def test_a_cantonese_question_round_trips_and_other_entries_keep_their_bytes(self):
        question = "電池座用邊一款？👍"
        path = self.mailbox(entry("q-1", status="answered", answer="用 47900"))
        before = path.read_text(encoding="utf-8")
        env = small_env()
        env["PYTHONUTF8"] = "0"
        done = self.run_tool(path, "ask", "--project", "General", "--task", "試", "--asked-by", "May", question,
                             env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        text = path.read_text(encoding="utf-8")
        self.assertIn('"question": "%s"' % question, text)
        self.assertEqual(json.loads(text)["questions"][1]["question"], question)
        # The first entry, up to its closing brace, keeps every byte.
        first_end = before.rindex("}", 0, before.rindex("]"))
        self.assertEqual(text[:first_end], before[:first_end])

    def test_a_mailbox_with_a_byte_order_mark_takes_a_question_and_is_written_without_one(self):
        path = self.mailbox(entry("q-1"))
        path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8-sig")
        done = self.ask(path)
        self.assertEqual(done.returncode, 0, done.stderr)
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", raw)
        self.assertEqual(len(json.loads(raw.decode("utf-8"))["questions"]), 2)

    def test_ask_holds_its_own_lock_while_it_writes(self):
        tool, path = self.tool(), self.mailbox(entry("q-1"))
        lock = Path(str(path) + ".lock")
        real_write, holders = tool["write_atomic"], []

        def checked(target, *args, **kwargs):
            holders.append(lock.read_text(encoding="utf-8").split(" ")[0] if lock.exists() else "no lock")
            return real_write(target, *args, **kwargs)
        with mock.patch.dict(tool, {"write_atomic": checked}):
            self.assertEqual(self.call(tool, path, *ASK)[0], 0)
        self.assertEqual(holders, [str(os.getpid())])

    @unittest.skipUnless(NODE, "node is not on PATH")
    def test_ask_waits_while_the_servers_own_lock_exists(self):
        path = self.mailbox(entry("q-1"))
        # The lock file the server's answerQuestion opens, read from its own exclusive open, never assumed.
        spy = ("import fs from 'node:fs'; import { syncBuiltinESMExports } from 'node:module';"
               " const open = fs.openSync;"
               " fs.openSync = (file, flags, ...rest) => { if (flags === 'wx') console.log(file); return open(file, flags, ...rest); };"
               " syncBuiltinESMExports();"
               " const { answerQuestion } = await import(process.argv[1]);"
               " await answerQuestion(process.argv[2], 'q-1', 'Yes');")
        done = subprocess.run([NODE, "--input-type=module", "-e", spy, QUESTIONS_MJS.as_uri(), str(path)],
                              capture_output=True, text=True, encoding="utf-8", timeout=30, env=small_env(),
                              creationflags=NO_WINDOW)
        self.assertEqual(done.returncode, 0, done.stderr)
        lock = Path(done.stdout.strip())
        lock.write_text("999 the server, still at work", encoding="utf-8")
        before = path.read_bytes()
        proc = subprocess.Popen([sys.executable, str(TOOL), *ASK, "--questions", str(path)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                env=small_env(), creationflags=NO_WINDOW)
        self.addCleanup(proc.kill)
        time.sleep(1)
        self.assertIsNone(proc.poll(), "ask wrote while the server's lock was held")
        self.assertEqual(path.read_bytes(), before)
        lock.unlink()
        out, err = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 0, err)
        self.assertEqual([q["id"] for q in json.loads(path.read_text(encoding="utf-8"))["questions"]],
                         ["q-1", out.strip()])

    def test_a_folder_that_refuses_the_lock_is_waited_on_to_the_bound_then_exits_4(self):
        tool, path = self.tool(), self.mailbox(entry("q-1"))
        before, real_open, tries = path.read_bytes(), os.open, []

        # Windows reports a folder that refuses file creation as PermissionError, and no lock ever appears.
        def refused(name, *args, **kwargs):
            if not str(name).endswith(".lock"):
                return real_open(name, *args, **kwargs)
            tries.append(name)
            if len(tries) > 1000:  # a guard, so a loop that never sleeps fails here instead of hanging
                raise OSError(errno.ELOOP, "opened without a pause")
            raise PermissionError(errno.EACCES, "Permission denied")
        with mock.patch.dict(tool, {"LOCK_WAIT": 0.2}), mock.patch.object(os, "open", refused):
            code, err = self.call(tool, path, *ASK)
        self.assertEqual(code, 4, err)
        self.assertLess(len(tries), 50)
        self.assertEqual(path.read_bytes(), before)

    def test_a_replace_a_reader_refuses_is_tried_again_and_the_question_lands(self):
        tool, path = self.tool(), self.mailbox(entry("q-1"))
        real_replace, refused = os.replace, []

        # On Windows a replace over a file another process has open, such as a `dashboard wait` poll, fails.
        def busy_at_first(src, dst):
            if len(refused) < 3:
                refused.append(dst)
                raise PermissionError(errno.EACCES, "Access is denied")
            return real_replace(src, dst)
        with mock.patch.object(os, "replace", busy_at_first):
            code, err = self.call(tool, path, *ASK)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(refused), 3)
        self.assertEqual(len(json.loads(path.read_text(encoding="utf-8"))["questions"]), 2)
        self.assertEqual(os.listdir(path.parent), ["questions.json"])

    def test_a_replace_refused_through_every_retry_exits_4_and_leaves_no_scratch_file(self):
        tool, path = self.tool(), self.mailbox(entry("q-1"))
        before = path.read_bytes()
        with mock.patch.object(os, "replace", side_effect=PermissionError(errno.EACCES, "Access is denied")):
            code, err = self.call(tool, path, *ASK)
        self.assertEqual(code, 4, err)
        self.assertIn("busy", err)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(os.listdir(path.parent), ["questions.json"])

    def test_a_token_write_that_fails_lets_go_of_the_lock(self):
        tool, path = self.tool(), self.mailbox(entry("q-1"))
        # A full disk refuses the token, here as the lock's descriptor is opened for writing.
        with mock.patch.object(os, "fdopen", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            code, err = self.call(tool, path, *ASK)
        self.assertEqual(code, 1, err)
        self.assertFalse(Path(str(path) + ".lock").exists())
        with mock.patch.dict(tool, {"LOCK_WAIT": 0.3}):
            self.assertEqual(self.call(tool, path, *ASK)[0], 0, "the next writer is shut out")

    def test_a_byte_order_mark_counts_as_blank_as_the_servers_trim_does(self):
        tool, path = self.tool(), self.mailbox(entry("q-1", status="answered", answer="Yes"))
        before = path.read_bytes()
        for args in (("ask", "--project", "PCB", "--task", "t", "--asked-by", "May", BOM),
                     ("ask", "--project", "PCB", "--task", "t", "--asked-by", " " + BOM, "Q?"),
                     ("used", "q-1", "--by", BOM, "--note", "Done."),
                     ("used", "q-1", "--by", "May", "--note", BOM + " ")):
            with self.subTest(args=args):
                code, err = self.call(tool, path, *args)
                self.assertEqual(code, 2, err)
                self.assertIn("must not be empty", err)
        self.assertEqual(path.read_bytes(), before)
        code, err = self.call(tool, path, "ask", "--project", "PCB", "--task", BOM + " Order " + BOM,
                              "--asked-by", BOM + "May", " " + BOM + "Which holder?" + BOM)
        self.assertEqual(code, 0, err)
        added = json.loads(path.read_text(encoding="utf-8"))["questions"][1]
        self.assertEqual([added["task"], added["asked_by"], added["question"]], ["Order", "May", "Which holder?"])
        # A question of only U+FEFF makes the server refuse the whole file, so the command does too.
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["questions"][0]["question"] = BOM
        self.save(path, doc)
        code, err = self.call(tool, path, *ASK)
        self.assertEqual(code, 1, err)
        self.assertIn("not valid at questions[0].question", err)

    def test_blank_means_what_javascripts_trim_takes_off_no_more(self):
        trimmed = self.tool()["trimmed"]
        for c in (" ", "\t", "\n", chr(0xA0), chr(0x2028), chr(0x3000), BOM):
            with self.subTest(blank=hex(ord(c))):
                self.assertEqual(trimmed(c + "Q" + c), "Q")
        # Python's isspace() also takes these; JavaScript's trim() keeps them, so the server serves them.
        for c in ("\x1c", "\x1d", "\x1e", "\x1f", "\x85"):
            with self.subTest(kept=hex(ord(c))):
                self.assertEqual(trimmed(c + "Q" + c), c + "Q" + c)

    def test_a_long_run_of_inner_spaces_trims_at_once_while_the_lock_is_held(self):
        trimmed = self.tool()["trimmed"]
        text = "a" + " " * 40_000 + "b"
        started = time.monotonic()
        self.assertEqual(trimmed(" " + text + " "), text)
        self.assertLess(time.monotonic() - started, 0.5)

    def test_a_mailbox_file_marked_read_only_is_refused_at_once_not_called_busy(self):
        tool, path = self.tool(), self.mailbox(entry("q-1"))
        before, tries = path.read_bytes(), []
        os.chmod(path, stat.S_IREAD)
        self.addCleanup(os.chmod, path, stat.S_IREAD | stat.S_IWRITE)

        # Windows refuses a replace over a read-only file for good; no reader is to blame.
        def refused(src, dst):
            tries.append(dst)
            raise PermissionError(errno.EACCES, "Access is denied")
        with mock.patch.object(os, "replace", refused):
            code, err = self.call(tool, path, *ASK)
        self.assertEqual(code, 1, err)
        self.assertIn("cannot change", err)
        self.assertEqual(len(tries), 1, "not retried")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(os.listdir(path.parent), ["questions.json"])


if __name__ == "__main__":
    unittest.main()
