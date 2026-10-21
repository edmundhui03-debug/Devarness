"""agent-memory: where Peter's Claude Code memory lives, and a check of its index and files.

Run: python3 Library/tests/test_agent_memory.py
 or: python3 -m unittest discover -s Library/tests -p 'test_agent_memory.py'

Every fixture is written into a temporary folder; no real memory folder is read.
The slug expectations were produced by running Claude Code 2.1.274's own
JavaScript slug functions under node, not by this tool.
"""
from __future__ import annotations

import contextlib
from datetime import date
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "agent-memory"
LOADER = importlib.machinery.SourceFileLoader("agent_memory", str(SCRIPT))
SPEC = importlib.util.spec_from_loader("agent_memory", LOADER)
MEMORY = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MEMORY)

TODAY = date(2026, 9, 17)
LOCATION_VARIABLES = ("DEVARNESS_MEMORY_DIR", "CLAUDE_CONFIG_DIR")
# Built from parts, so the sync's portability guard does not read this check
# as a machine path it should refuse.
MACHINE_PATH = re.compile("|".join(("/" + "Users/[a-zA-Z]", "C:" + r"\\" + "Users" + r"\\", "/" + "home/[a-z]",
                                    "/private" + "/tmp/", "/" + "Applications/")))
PROSE = ("Kept by Peter, one bullet per memory. This paragraph is prose rather than an index line, so neither "
         "its length nor [a link to a file that is not there](missing-notes.md) is an index finding."
         + " It goes on about how the index is kept." * 6)
TOOL_NOTES_LINE = "- [Tool notes](reference-tool-notes.md) — where ngspice lives and how it runs headless"
USER_DESCRIPTION = 'description: "The owner reviews \\"every\\" board before fabrication and reads Markdown in vim"'
TOOL_DESCRIPTION = "description: >-\n  Where the spice simulator lives and\n  which flags make it run headless"


def run(*argv, today=TODAY):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = MEMORY.main(list(argv), today=lambda: today)
    return code, out.getvalue(), err.getvalue()


def clean_memory():
    """Four memories in the shapes real ones take: extra metadata keys, a trailing
    space after `metadata:`, quoted and folded descriptions, comments, labelled
    links, `[[names]]` inside code that are not links, and an index with prose."""
    if len(PROSE) <= 300:
        raise AssertionError("the prose line must be longer than an index line may be")
    return {
        "MEMORY.md": "\n".join([
            "# Memory index",
            "",
            PROSE,
            "",
            "- [Owner role](user-owner-role.md) — reviews every board before fabrication; reads Markdown in "
            "[vim](https://www.vim.org)",
            "- [Small commits](feedback-small-commits.md) — commit by path, never sweep another session's staged files",
            "- [Bridge build](project-bridge-build.md) — checkpoint 4 accepted, sign-off pending; "
            "see [[project-bridge-build]]",
            TOOL_NOTES_LINE,
            "",
        ]),
        "user-owner-role.md": "\n".join([
            "---",
            "name: user-owner-role",
            USER_DESCRIPTION,
            "metadata: ",
            "  node_type: memory",
            "  type: user",
            "  originSessionId: 7b0196ae-bbad-4cea-ad2a-eca98afa6a5c",
            "  modified: 2026-09-01T08:00:00.000Z",
            "---",
            "",
            "The owner is an electronics engineer; see [[feedback-small-commits]].",
            "",
        ]),
        "feedback-small-commits.md": "\n".join([
            "---",
            "name: feedback-small-commits",
            "description: Commit by path so another session's staged files never ride along",
            "metadata:",
            "  type: feedback",
            "---",
            "",
            "Commit with `git commit --only <paths>`; `[[in-code-span]]` is not a link.",
            "",
            "**Why:** a plain commit swept another session's staged work on 2026-09-10.",
            "",
            "**How to apply:** name every path in the commit command.",
            "",
        ]),
        "project-bridge-build.md": "\n".join([
            "---",
            "# written by hand",
            "name: project-bridge-build",
            "description: 'Bridge controller build: checkpoint 4 accepted, the owner''s sign-off pending'",
            "metadata:",
            "  type: project  # a trailing comment",
            "  modified: 2026-09-03T10:00:00.000Z",
            "---",
            "",
            "Checkpoint 4 was accepted on 2026-09-12 (the vendor's tag 9999-99-99 is not a date); "
            "see [[user-owner-role]] and [[reference-tool-notes|the notes]].",
            "",
            "- **Why:** the owner asked for staged delivery.",
            "- **How to apply:** resume from checkpoint 4.",
            "",
        ]),
        "reference-tool-notes.md": "\n".join([
            "---",
            "name: reference-tool-notes",
            TOOL_DESCRIPTION,
            "metadata:",
            "  type: reference",
            "---",
            "",
            "ngspice runs in batch mode with -b.",
            "",
            "```text",
            "[[fenced-example]] stays inside a code block",
            "```",
            "",
        ]),
    }


def write(folder, files, encoding="utf-8", newline="\n"):
    for name, text in files.items():
        with open(os.path.join(folder, name), "w", encoding=encoding, newline=newline) as handle:
            handle.write(text)


def edit(files, name, old, new):
    if old not in files[name]:
        raise AssertionError(f"fixture text {old!r} is not in {name}")
    files[name] = files[name].replace(old, new, 1)


def link_a_missing_file(files):
    files["MEMORY.md"] += "- [Ghost](project-ghost.md) — a memory that was never written\n"


def leave_a_file_out_of_the_index(files):
    files["reference-bench-serial.md"] = "\n".join([
        "---", "name: reference-bench-serial", "description: Serial console baud rates for the lab bench adapters",
        "metadata:", "  type: reference", "---", "", "Most adapters run at 115200.", ""])


def drop_the_front_matter(files):
    files["reference-tool-notes.md"] = "ngspice runs in batch mode with -b.\n"


def leave_the_front_matter_open(files):
    edit(files, "reference-tool-notes.md", "  type: reference\n---\n", "  type: reference\n")


def break_a_front_matter_line(files):
    edit(files, "reference-tool-notes.md", "name: reference-tool-notes\n",
         "name: reference-tool-notes\nthis line is not a key\n")


def rename_a_memory(files):
    edit(files, "user-owner-role.md", "name: user-owner-role", "name: owner-role")


def drop_a_name(files):
    edit(files, "user-owner-role.md", "name: user-owner-role\n", "")


def use_an_unknown_type(files):
    edit(files, "reference-tool-notes.md", "  type: reference", "  type: decision")


def drop_a_type(files):
    edit(files, "reference-tool-notes.md", "  type: reference\n", "  node_type: memory\n")


def lengthen_an_index_line(files):
    edit(files, "MEMORY.md", "how it runs headless", "how it runs headless" + ", and why" * 30)


def age_a_project(files):
    edit(files, "project-bridge-build.md", "on 2026-09-12", "on 2026-08-20")
    edit(files, "project-bridge-build.md", "modified: 2026-09-03", "modified: 2026-08-19")


def drop_how_to_apply(files):
    edit(files, "feedback-small-commits.md", "**How to apply:** name", "Name")


def drop_why(files):
    edit(files, "project-bridge-build.md", "- **Why:** the owner", "- The owner")


def copy_a_description(files):
    edit(files, "reference-tool-notes.md", TOOL_DESCRIPTION,
         "description: The owner reviews every board before fabrication and reads Markdown daily")


def link_an_unwritten_memory(files):
    edit(files, "reference-tool-notes.md", "with -b.", "with -b; see [[never-written]].")


KNOWN_BAD = (
    ("M001", "MEMORY.md", 9, "links project-ghost.md", link_a_missing_file),
    ("M002", "reference-bench-serial.md", 1, "not linked from MEMORY.md", leave_a_file_out_of_the_index),
    ("M003", "reference-tool-notes.md", 1, "no front matter", drop_the_front_matter),
    ("M003", "reference-tool-notes.md", 1, "not closed", leave_the_front_matter_open),
    ("M003", "reference-tool-notes.md", 3, "this line is not a key", break_a_front_matter_line),
    ("M004", "user-owner-role.md", 2, "'owner-role' differs from the file stem 'user-owner-role'", rename_a_memory),
    ("M004", "user-owner-role.md", 1, "name is missing", drop_a_name),
    ("M005", "reference-tool-notes.md", 7, "type 'decision' is not one of", use_an_unknown_type),
    ("M005", "reference-tool-notes.md", 6, "type is missing", drop_a_type),
    ("M101", "MEMORY.md", 8, "over 300", lengthen_an_index_line),
    ("M102", "project-bridge-build.md", 10, "2026-08-20, 28 days before 2026-09-17", age_a_project),
    ("M103", "feedback-small-commits.md", 1, "no 'How to apply:' line", drop_how_to_apply),
    ("M103", "project-bridge-build.md", 1, "no 'Why:' line", drop_why),
    ("M104", "user-owner-role.md", 3, "similar to reference-tool-notes.md", copy_a_description),
    ("M201", "reference-tool-notes.md", 10, "[[never-written]] names no existing memory", link_an_unwritten_memory),
)


class Scratch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # resolve(): TEMP may hold an 8.3 short name; the tool prints the long one.
        self.tmp = Path(tmp.name).resolve()

    def folder_with(self, *mutations):
        files = clean_memory()
        for mutate in mutations:
            mutate(files)
        folder = tempfile.mkdtemp(dir=str(self.tmp))
        write(folder, files)
        return folder

    def findings(self, folder, today=TODAY):
        code, out, err = run("check", "--dir", folder, "--json", today=today)
        return json.loads(out)["findings"]

    def positions(self, folder, today=TODAY):
        return [(finding["code"], finding["file"], finding["line"]) for finding in self.findings(folder, today)]

    def codes(self, folder, today=TODAY):
        return [code for code, _, _ in self.positions(folder, today)]


class ClaudeCodeSlug(Scratch):
    def test_every_character_but_an_ascii_letter_or_digit_becomes_one_dash(self):
        for path, expected in (("/opt/work/dev", "-opt-work-dev"),
                               ("/srv/PCB Tools/AGENTS/Example_App", "-srv-PCB-Tools-AGENTS-PCB-Studio"),
                               ("/tmp/claude-501/-srv-dev/scratchpad", "-tmp-claude-501--srv-dev-scratchpad")):
            with self.subTest(path=path):
                self.assertEqual(MEMORY.slug(path), expected)

    def test_a_windows_drive_path_dashes_the_colon_and_every_separator(self):
        for path, expected in (("C:\\Work\\dev", "C--Work-dev"), ("D:/Projects/dev", "D--Projects-dev")):
            with self.subTest(path=path):
                self.assertEqual(MEMORY.slug(path), expected)

    def test_characters_beyond_ascii_count_as_javascript_counts_them_after_nfc(self):
        composed = "/srv/caf\u00e9/\U0001F600/dev"
        self.assertEqual(MEMORY.slug(composed), "-srv-caf-----dev")
        self.assertEqual(MEMORY.slug(unicodedata.normalize("NFD", composed)), "-srv-caf-----dev")

    def test_a_slug_past_200_characters_is_cut_and_given_claude_codes_hash(self):
        posix = "/srv/" + "a long folder name/" * 11 + "dev"
        windows = "E:\\" + "Deep Folder\\" * 18 + "dev"
        self.assertEqual(MEMORY.slug(posix), "-srv-" + "a-long-folder-name-" * 10 + "a-lon-illqud")
        self.assertEqual(MEMORY.slug(windows), "E--" + "Deep-Folder-" * 16 + "Deep--eiwcvu")


class WhereTheMemoryLives(Scratch):
    def environment(self, **values):
        env = {key: value for key, value in os.environ.items() if key not in LOCATION_VARIABLES}
        env.update(values)
        return env

    def fake_root(self):
        root = self.tmp / "Fake dev root"
        (root / "Library" / "bin").mkdir(parents=True)
        shutil.copy2(str(SCRIPT), str(root / "Library" / "bin" / "agent-memory"))
        return root

    def where(self, tool, *argv, home, cwd=None, **values):
        env = self.environment(HOME=str(home), USERPROFILE=str(home), **values)
        return subprocess.run([sys.executable, str(tool), "where", *argv], capture_output=True, text=True,
                              env=env, cwd=cwd, timeout=60)

    def test_the_dir_option_wins_over_dev_memory_dir(self):
        chosen, ignored = self.tmp / "chosen", self.tmp / "ignored"
        with mock.patch.dict(os.environ, self.environment(DEVARNESS_MEMORY_DIR=str(ignored)), clear=True):
            self.assertEqual(run("where", "--dir", str(chosen))[:2], (0, f"{chosen}\n"))

    def test_dev_memory_dir_is_used_when_no_dir_option_is_given(self):
        chosen = self.tmp / "from-environment"
        env = self.environment(DEVARNESS_MEMORY_DIR=str(chosen), CLAUDE_CONFIG_DIR=str(self.tmp / "config"))
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(run("where")[:2], (0, f"{chosen}\n"))

    def test_a_relative_or_home_relative_folder_is_printed_absolute(self):
        home = self.tmp / "home"
        relative = self.where(SCRIPT, "--dir", "memory", home=home, cwd=str(self.tmp))
        tilde = self.where(SCRIPT, home=home, DEVARNESS_MEMORY_DIR="~/memory")
        self.assertEqual(relative.stdout, f"{os.path.join(os.path.realpath(str(self.tmp)), 'memory')}\n")
        self.assertEqual(tilde.stdout, f"{home / 'memory'}\n")

    def test_without_either_the_folder_is_derived_from_the_root_under_home(self):
        root, home = self.fake_root(), self.tmp / "home"
        result = self.where(root / "Library" / "bin" / "agent-memory", home=home)
        name = re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))
        self.assertEqual((result.returncode, result.stdout),
                         (0, f"{home / '.claude' / 'projects' / name / 'memory'}\n"), result.stderr)

    def test_claude_config_dir_takes_the_place_of_the_claude_folder_in_home(self):
        root, home, config = self.fake_root(), self.tmp / "home", self.tmp / "config"
        result = self.where(root / "Library" / "bin" / "agent-memory", home=home, CLAUDE_CONFIG_DIR=str(config))
        name = re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))
        self.assertEqual((result.returncode, result.stdout),
                         (0, f"{config / 'projects' / name / 'memory'}\n"), result.stderr)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_a_linked_worktree_maps_to_its_main_checkout_as_claude_code_does(self):
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME="agent-memory test", GIT_AUTHOR_EMAIL="test@example.invalid",
                   GIT_COMMITTER_NAME="agent-memory test", GIT_COMMITTER_EMAIL="test@example.invalid")

        def git(*args):
            return subprocess.run(["git", *args], check=True, capture_output=True, text=True, input="",
                                  env=env, timeout=60).stdout.strip()

        same = os.path.realpath
        main, linked = self.tmp / "dev", self.tmp / "dev worktree"
        git("init", "-q", str(main))
        git("-C", str(main), "commit", "-q", "--allow-empty", "-m", "start")
        git("-C", str(main), "worktree", "add", "-q", "--detach", str(linked))
        self.assertEqual(same(MEMORY.canonical_root(str(linked))), same(str(main)))
        self.assertEqual(MEMORY.canonical_root(str(main)), str(main))

        copied = self.tmp / "copied worktree"  # its gitdir still links back to the original
        shutil.copytree(str(linked), str(copied))
        self.assertEqual(MEMORY.canonical_root(str(copied)), str(copied))

        bare, bare_linked = self.tmp / "bare.git", self.tmp / "bare worktree"
        git("init", "-q", "--bare", str(bare))
        commit = git("-C", str(bare), "commit-tree", git("-C", str(bare), "mktree"), "-m", "start")
        git("-C", str(bare), "worktree", "add", "-q", "--detach", str(bare_linked), commit)
        self.assertEqual(same(MEMORY.canonical_root(str(bare_linked))), same(str(bare)))
        (bare / ".git").write_text("", encoding="utf-8")
        self.assertEqual(MEMORY.canonical_root(str(bare_linked)), str(bare_linked))

        crafted = self.tmp / "crafted"  # a commondir, but a gitdir outside <common>/worktrees
        (crafted / "meta").mkdir(parents=True)
        (crafted / ".git").write_text("gitdir: meta\n", encoding="utf-8")
        (crafted / "meta" / "commondir").write_text(os.path.join("..", "..", "dev", ".git") + "\n", encoding="utf-8")
        (crafted / "meta" / "gitdir").write_text(str(crafted / ".git") + "\n", encoding="utf-8")
        self.assertEqual(MEMORY.canonical_root(str(crafted)), str(crafted))

        submodule = self.tmp / "submodule"
        submodule.mkdir()
        (submodule / ".git").write_text("gitdir: ../dev/.git/modules/submodule\n", encoding="utf-8")
        self.assertEqual(MEMORY.canonical_root(str(submodule)), str(submodule))

        # Every assertion above calls canonical_root itself, so deleting its one use in
        # memory_folder() would leave them all green while `where` and `check` answered
        # with the worktree's own slug. Run the tool the way an isolated subagent does.
        for tree in (main, linked):
            (tree / "Library" / "bin").mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(SCRIPT), str(tree / "Library" / "bin" / "agent-memory"))
        home = self.tmp / "worktree home"
        printed = self.where(linked / "Library" / "bin" / "agent-memory", home=home)
        folder = re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(str(main)))
        self.assertEqual((printed.returncode, printed.stdout),
                         (0, f"{home / '.claude' / 'projects' / folder / 'memory'}\n"), printed.stderr)


class FrontMatterReader(unittest.TestCase):
    def test_the_reader_returns_the_values_yaml_would_for_the_shapes_it_accepts(self):
        lines = ["---", "# a comment", 'name: "caf\\u00e9 \\"quoted\\""', "description: 'it''s: fine'",
                 "plain: value with: colon  # comment", "folded: >-", "  first part", "  second part",
                 "literal: |", "  line one", "  line two", "wrapped: a plain value", "  that continues",
                 "metadata: ", "  type: user", "  deeper:", "    ignored: true", "tags:", "  - one", "  - 'two'",
                 "empty:", "---", "body"]
        fields, where, body = MEMORY.read_front_matter(lines)
        self.assertEqual(fields, {
            "name": 'caf\u00e9 "quoted"', "description": "it's: fine", "plain": "value with: colon",
            "folded": "first part second part", "literal": "line one\nline two",
            "wrapped": "a plain value that continues", "metadata": {"type": "user", "deeper": None},
            "tags": ["one", "two"], "empty": None})
        self.assertEqual((where["name"], where["metadata.type"], body), (3, 15, 22))

    def test_the_reader_refuses_each_malformed_shape_at_its_line(self):
        for text, line in (('description: "never closed', 2), ("description: 'never closed", 2),
                           ('description: "closed" then text', 2), ("description: 'closed' then text", 2),
                           ('description: "bad \\q escape"', 2), ("  indented: with no key above", 2),
                           ("not a key line", 2), ("description: >x", 2),
                           ('description: "quoted"\n  continued', 3), ("description: plain\n  key: under it", 3),
                           ("name: a\nname: b", 3), ("metadata:\n  not a key", 3),
                           ("metadata:\n  type: user\n node_type: memory", 4), ("metadata:\n  - item\n  type: user", 4),
                           ("metadata:\n  type: user\n  - item", 4), ("metadata:\n  type: user\n  type: feedback", 4)):
            with self.subTest(text=text):
                with self.assertRaises(MEMORY.FrontMatterError) as caught:
                    MEMORY.read_front_matter(["---", *text.split("\n"), "---", "body"])
                self.assertEqual(caught.exception.line, line)


class CheckFindings(Scratch):
    def test_a_clean_folder_passes_with_no_findings_and_exits_0(self):
        folder = self.folder_with()
        code, out, err = run("check", "--dir", folder)
        self.assertEqual((code, out.splitlines()),
                         (0, [f"checked 4 memory files in {folder}: 0 errors, 0 warnings, 0 info"]), err)

    def test_each_known_bad_fixture_raises_exactly_its_own_code_at_its_line_and_says_why(self):
        for code, file, line, words, mutate in KNOWN_BAD:
            with self.subTest(fixture=mutate.__name__):
                findings = self.findings(self.folder_with(mutate))
                self.assertEqual([(f["code"], f["file"], f["line"]) for f in findings], [(code, file, line)])
                self.assertIn(words, findings[0]["message"])

    def test_an_error_exits_1_and_warnings_or_information_alone_exit_0(self):
        for mutate, expected in ((link_a_missing_file, 1), (drop_a_type, 1), (lengthen_an_index_line, 0),
                                 (drop_how_to_apply, 0), (link_an_unwritten_memory, 0)):
            with self.subTest(fixture=mutate.__name__):
                self.assertEqual(run("check", "--dir", self.folder_with(mutate))[0], expected)

    def test_usage_errors_and_a_folder_that_does_not_exist_exit_2(self):
        for argv in ([], ["check", "--bogus"], ["sweep"], ["check", "--dir", str(self.tmp / "absent")]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)

    def test_json_parses_and_matches_the_text_findings(self):
        folder = self.folder_with(link_a_missing_file, lengthen_an_index_line, age_a_project,
                                  link_an_unwritten_memory)
        text_code, text, _ = run("check", "--dir", folder)
        json_code, raw, _ = run("check", "--dir", folder, "--json")
        report = json.loads(raw)
        self.assertEqual((text_code, json_code), (1, 1))
        self.assertEqual(list(report), ["folder", "files", "errors", "warnings", "info", "findings"])
        self.assertEqual([report[key] for key in ("folder", "files", "errors", "warnings", "info")],
                         [folder, 4, 1, 2, 1])
        levels = {"M0": "error", "M1": "warning", "M2": "info"}
        for finding in report["findings"]:
            self.assertEqual(list(finding), ["level", "code", "file", "line", "message"])
            self.assertEqual(finding["level"], levels[finding["code"][:2]])
        lines = [f"{f['file']}:{f['line']}: {f['code']} {f['message']}" for f in report["findings"]]
        self.assertEqual(len(lines), 4)
        self.assertEqual(text.splitlines(),
                         lines + [f"checked 4 memory files in {folder}: 1 error, 2 warnings, 1 info"])

    def test_a_project_memory_warns_only_when_its_newest_date_is_over_14_days_old(self):
        def leave_only_the_front_matter_date_recent(files):
            edit(files, "project-bridge-build.md", "on 2026-09-12", "on 2026-08-20")

        folder = self.folder_with(leave_only_the_front_matter_date_recent)
        self.assertEqual(self.codes(folder, today=date(2026, 9, 17)), [])
        self.assertEqual(self.codes(folder, today=date(2026, 9, 18)), ["M102"])

    def test_an_index_line_warns_only_past_300_characters(self):
        for length, expected in ((300, []), (301, ["M101"])):
            def pad(files, length=length):
                edit(files, "MEMORY.md", TOOL_NOTES_LINE, TOOL_NOTES_LINE + "x" * (length - len(TOOL_NOTES_LINE)))

            with self.subTest(length=length):
                self.assertEqual(self.codes(self.folder_with(pad)), expected)

    def test_descriptions_are_near_duplicates_at_a_jaccard_of_0_6_and_not_below(self):
        for folded, expected in ((("alpha beta", "gamma epsilon"), ["M104"]),
                                 (("alpha beta gamma", "epsilon zeta"), [])):
            def describe(files, folded=folded):
                edit(files, "user-owner-role.md", USER_DESCRIPTION, "description: alpha beta gamma delta")
                edit(files, "reference-tool-notes.md", TOOL_DESCRIPTION, "description: >-\n  {}\n  {}".format(*folded))

            with self.subTest(folded=folded):
                self.assertEqual(self.codes(self.folder_with(describe)), expected)

    def test_a_top_level_type_counts_when_metadata_has_none_as_claude_code_merges_them(self):
        def top_level_only(files):
            edit(files, "reference-tool-notes.md", "metadata:\n  type: reference\n", "type: reference\n")

        def metadata_wins(files):
            edit(files, "reference-tool-notes.md", "metadata:\n  type: reference\n",
                 "type: decision\nmetadata:\n  type: reference\n")

        for mutate in (top_level_only, metadata_wins):
            with self.subTest(fixture=mutate.__name__):
                self.assertEqual(self.codes(self.folder_with(mutate)), [])

    def test_a_link_may_name_a_memory_by_its_name_or_by_its_file_stem(self):
        def link_by_name(files):
            rename_a_memory(files)
            edit(files, "reference-tool-notes.md", "with -b.", "with -b; ask [[owner-role]].")

        self.assertEqual(self.codes(self.folder_with(link_by_name)), ["M004"])

    def test_without_an_index_every_memory_file_is_unlinked(self):
        folder = self.folder_with()
        os.remove(os.path.join(folder, "MEMORY.md"))
        names = sorted(name for name in clean_memory() if name != "MEMORY.md")
        self.assertEqual(self.positions(folder), [("M002", name, 1) for name in names])

    def test_a_memory_file_that_is_not_utf8_is_unparseable_and_a_stray_byte_in_the_index_is_not(self):
        folder = self.folder_with()
        with open(os.path.join(folder, "reference-tool-notes.md"), "wb") as handle:
            handle.write(b"---\nname: reference-tool-notes\ndescription: caf\xe9\n---\n")
        with open(os.path.join(folder, "MEMORY.md"), "ab") as handle:
            handle.write(b"A stray Latin-1 byte: caf\xe9\n")
        self.assertEqual(self.positions(folder), [("M003", "reference-tool-notes.md", 1)])

    def test_a_byte_order_mark_and_crlf_line_endings_read_like_plain_lf(self):
        files = clean_memory()
        edit(files, "MEMORY.md", TOOL_NOTES_LINE, TOOL_NOTES_LINE + "x" * (300 - len(TOOL_NOTES_LINE)))
        folder = tempfile.mkdtemp(dir=str(self.tmp))
        write(folder, files, encoding="utf-8-sig", newline="\r\n")
        self.assertEqual(self.codes(folder), [])


class TheExecutable(Scratch):
    def test_the_script_runs_on_its_own_and_exits_0_1_or_2(self):
        clean, bad = self.folder_with(), self.folder_with(link_a_missing_file)
        for argv, expected in ((["check", "--dir", clean], 0), (["check", "--dir", bad, "--json"], 1),
                               (["check", "--nonsense"], 2)):
            with self.subTest(argv=argv):
                result = subprocess.run([sys.executable, str(SCRIPT), *argv],
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_the_tool_names_no_machine_specific_path(self):
        self.assertIsNone(MACHINE_PATH.search(SCRIPT.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
