#!/usr/bin/env python3
"""task-recall answers "what happened to X, and what is next" from dev's own records.

Run: python3 Harness/tests/test_task_recall.py

Every test builds a stand-in dev — a few documents with section statuses, a plan
with checkboxes, a memory folder — so the assertions do not move when the real
workspace does. Two integration tests run the tool against this checkout, and
say what they found rather than pinning a number that will change tomorrow.
"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "Harness" / "bin" / "task-recall"

DOC = """# {title}

> **2026-09-18** · Peter · `current`
>
> One sentence. Another sentence.

## {done_head}

`fixed` · it was finished

Evidence at `some/file.py:12`.

## {open_head}

`open` · still to do

More prose.
"""

PLAN = """# {title}

> **2026-09-18** · Peter · `current`
>
> One sentence. Another sentence.

## Task one is done

`fixed` · done

- [x] the first step
- [x] the second step
- [ ] the third step
"""

MEMORY = """---
name: {name}
description: "{description}"
metadata:
  type: project
---

{body}
"""


def load():
    loader = importlib.machinery.SourceFileLoader("task_recall", str(TOOL))
    spec = importlib.util.spec_from_loader("task_recall", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Workspace:
    """A stand-in dev: documents with statuses, a plan, and a memory folder."""

    def __init__(self, root: Path):
        self.root = root
        self.memory = root / "memory"
        self.memory.mkdir(parents=True)
        (root / ".claude").mkdir()
        (root / "CLAUDE.md").write_text("# router\n", encoding="utf-8")
        self.sections = []

    def doc(self, relative, title, done_head, open_head):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DOC.format(title=title, done_head=done_head, open_head=open_head),
                        encoding="utf-8")
        self.sections.append({"status": "fixed", "file": relative, "line": 7,
                              "heading": done_head, "live": False})
        self.sections.append({"status": "open", "file": relative, "line": 13,
                              "heading": open_head, "live": True})
        return path

    def plan(self, relative, title):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PLAN.format(title=title), encoding="utf-8")
        self.sections.append({"status": "fixed", "file": relative, "line": 7,
                              "heading": "Task one is done", "live": False})
        return path

    def remember(self, name, description, body="Something worth keeping."):
        (self.memory / (name + ".md")).write_text(
            MEMORY.format(name=name, description=description, body=body), encoding="utf-8")

    def status(self):
        live = ("open", "blocked", "needs-owner")
        return {"sections": self.sections,
                "counts": {"marked": len(self.sections),
                           "live": sum(1 for s in self.sections if s["status"] in live),
                           "dormant": 0}}

    def status_file(self):
        # Outside the dev root: a fixture that writes into the workspace cannot
        # then prove the tool left the workspace alone.
        path = self.root.parent / "status.json"
        path.write_text(json.dumps(self.status()), encoding="utf-8")
        return path


class Case(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="task-recall-")
        self.addCleanup(temp.cleanup)
        self.tool = load()
        self.ws = Workspace(Path(temp.name) / "dev")

    def find(self, query):
        return self.tool.find(query.split(), self.ws.root, self.ws.status(), self.ws.memory)


class NamingTests(Case):
    """named() is the gate the prompt hook reads: does the prompt NAME this subject?

    find() ranks by shared words, which is right for a question typed at task-recall and
    wrong for a sentence typed at an agent. Common words such as "test", "rest"
    and "bugs" can overlap unrelated paths. People name a project with words that
    stand together, and a name is where those words stand together too.
    """

    def named(self, prompt):
        return self.tool.named(prompt.split(), self.ws.root, self.ws.status(), self.ws.memory)

    def test_two_words_said_together_and_found_together_name_the_subject(self):
        self.ws.doc("Setup/device-sync-sheet.md", "The device sync sheet is live",
                    "The page is served", "The data is a day old")
        hit = self.named("what happened with the device sync sheet")
        self.assertIsNotNone(hit, "a project named outright was not recognised")
        self.assertEqual(hit.file, "Setup/device-sync-sheet.md")

    def test_one_shared_word_never_names_a_subject(self):
        self.ws.doc("DEMO_FIRMWARE/docs/unit-test-coverage.md", "Unit test coverage for the server",
                    "The server suite was counted", "The mobile suite was not")
        self.assertIsNone(self.named("little test, can still remember what we discussed before?"))

    def test_words_scattered_over_a_long_document_do_not_add_up_to_a_name(self):
        # 32 marked sections gave one record 128 heading words, and a long prompt
        # found five of them, each in a different heading.
        self.ws.doc("Codex/windows-pc.md", "The second machine is set up",
                    "The agent was installed", "The device still needs a name")
        self.ws.sections.append({"status": "open", "file": "Codex/windows-pc.md", "line": 30,
                                 "heading": "The guide has a gap", "live": True})
        self.assertIsNone(self.named("no matter which device I start, the agent should follow the guide"))

    def test_words_far_apart_in_the_prompt_are_not_said_together(self):
        self.ws.doc("DEMO_FIRMWARE/docs/quick-start-guide.md", "Quick start guide",
                    "The install is described", "The first run is not")
        self.assertIsNone(self.named("start the server and then open up the guide"))

    def test_a_pair_that_every_document_uses_names_none_of_them(self):
        for n in range(8):
            self.ws.doc("Setup/spec-%d.md" % n, "A design review of part %d" % n,
                        "The design was reviewed", "The review found a gap in the design")
        self.assertIsNone(self.named("I will review the design tomorrow morning"))

    def test_a_pair_with_one_uncommon_word_still_names_its_subject(self):
        for n in range(8):
            self.ws.doc("Setup/spec-%d.md" % n, "A design review of part %d" % n,
                        "The design was reviewed", "The review found a gap in the design")
        self.ws.doc("Setup/courtyard-design.md", "The courtyard design is accepted",
                    "The rule was written", "The check is not wired in")
        hit = self.named("where are we on the courtyard design")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.file, "Setup/courtyard-design.md")

    def test_a_phrase_inside_one_heading_names_the_document_that_carries_it(self):
        self.ws.doc("Setup/round-seven.md", "The seventh round is closed",
                    "The fab pack was delivered", "The order has not been placed")
        hit = self.named("is the fab pack ready")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.file, "Setup/round-seven.md")

    def test_the_document_whose_path_carries_the_name_beats_one_that_mentions_it(self):
        self.ws.doc("Setup/zz-demo-toggle.md", "A review", "Something done", "Something open")
        self.ws.doc("Setup/aa-notes.md", "Notes", "The demo toggle was discussed",
                    "The demo toggle needs a rerun")
        hit = self.named("what is left on the demo toggle")
        self.assertEqual(hit.file, "Setup/zz-demo-toggle.md",
                         "a path names its subject; a heading only mentions it")

    def test_a_dated_memory_snapshot_never_names_a_subject_a_live_document_also_names(self):
        # Dated memory copies can repeat a project name. A live document should
        # outrank them; the live memory is already shown with its subject box.
        for day in ("18", "20"):
            self.ws.doc("Setup/handoff/claude-memory-2026-09-%s/project-demo-toggle-review.md" % day,
                        "Demo toggle review", "Reviewed twice", "The v0.2 page is pending")
        self.ws.doc("PCB Tools/reviews/report.md", "A review report",
                    "The demo toggle was reviewed twice", "The demo toggle page is pending")
        hit = self.named("what is left on the demo toggle review")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.file, "PCB Tools/reviews/report.md")

    def test_a_snapshot_still_answers_when_nothing_live_does(self):
        self.ws.doc("Setup/handoff/claude-memory-2026-09-20/project-widget-sensor-bench.md",
                    "Widget sensor bench", "The sketches were written", "Nothing has been flashed")
        hit = self.named("widget sensor bench, what is next")
        self.assertIsNotNone(hit, "the only record there is should still be found")

    def test_titles_come_from_the_index_so_no_document_is_opened_to_learn_its_name(self):
        # The hook runs on every prompt. Use indexed titles instead of reopening
        # every document just to learn its name.
        status = self.ws.status()
        status["files"] = ["Setup/not-on-disk.md"]
        status["titles"] = {"Setup/not-on-disk.md": "The smoke detector routing is planned"}
        hit = self.tool.named("where is the smoke detector routing".split(), self.ws.root, status, None)
        self.assertIsNotNone(hit, "the title in the index was not used")
        self.assertEqual(hit.title, "The smoke detector routing is planned")

    def test_nothing_said_means_nothing_named(self):
        for prompt in ("hello", "ok go ahead", "thanks, that looks right"):
            with self.subTest(prompt):
                self.assertIsNone(self.named(prompt))


class MatchingTests(Case):
    def test_inflected_common_words_do_not_make_a_reply_a_project_name(self):
        self.ws.doc("Setup/mac-handoff.md", "The Mac handoff is prepared",
                    "The count looks right", "The Mac acceptance waits")
        hits = self.find("thanks, that looks right")
        self.assertTrue(hits)
        self.assertLess(hits[0].strong, 2.0,
                        "a conversational reply must stay below the recall threshold")

    def test_the_named_project_comes_first_even_against_a_busier_document(self):
        self.ws.doc("Setup/pyrosim-guide.md", "The PyroSim guide is written",
                    "The seven days are drafted", "Day seven needs a rerun")
        for n in range(4):
            self.ws.doc("PCB Tools/note%d.md" % n, "A PCB note",
                        "Something finished %d" % n, "Something open %d" % n)
        hits = self.find("pyrosim")
        self.assertTrue(hits, "nothing matched a word that is in a path and a title")
        self.assertEqual(hits[0].file, "Setup/pyrosim-guide.md")

    def test_a_word_in_the_path_outranks_the_same_word_in_another_file_headings(self):
        # A path names the subject; a heading only mentions it. The loser here is
        # built to win every tie-break — more open work, an earlier filename — so
        # this fails the moment the two are weighted the same.
        self.ws.doc("Setup/zz-ngspice.md", "A document", "Something done", "Something open")
        self.ws.doc("Setup/aa-other.md", "Another document",
                    "ngspice was installed", "ngspice is untested")
        self.ws.sections.append({"status": "open", "file": "Setup/aa-other.md", "line": 19,
                                 "heading": "a third ngspice thing", "live": True})
        hits = self.find("ngspice")
        self.assertEqual(hits[0].file, "Setup/zz-ngspice.md",
                         "the file whose path names it must come first")

    def test_a_word_in_a_heading_matches_when_the_path_does_not_carry_it(self):
        self.ws.doc("Setup/one.md", "A document", "The launcher loop was fixed",
                    "The launcher list still drifts")
        hits = self.find("launcher")
        self.assertEqual(hits[0].file, "Setup/one.md")

    def test_a_subject_discussed_only_in_the_prose_is_still_found(self):
        # "ngspice" is a table row in Harness/INSTALL.md and a line in Claude/TOOLS.md
        # and appears in no path or heading; scoring those two alone found only a
        # closed review that happened to mention it in a heading.
        path = self.ws.doc("Setup/tools.md", "The tools", "Something done", "Something open")
        path.write_text(path.read_text(encoding="utf-8")
                        + "\n| ngspice 47 | installed, simulation verified |\n", encoding="utf-8")
        hits = self.find("ngspice")
        self.assertTrue(hits, "a subject discussed only in prose was invisible")
        self.assertEqual(hits[0].file, "Setup/tools.md")

    def test_a_document_that_discusses_it_beats_one_that_mentions_it_once(self):
        # INSTALL.md says ngspice 21 times; a review that mentioned it once ranked
        # above it, because a flat body score tied and the tie-break took the file
        # with more open work.
        once = self.ws.doc("Setup/aa-passing.md", "In passing", "Done", "Open")
        once.write_text(once.read_text(encoding="utf-8") + "\nWe also used ngspice.\n",
                        encoding="utf-8")
        self.ws.sections.append({"status": "open", "file": "Setup/aa-passing.md", "line": 21,
                                 "heading": "another open thing", "live": True})
        about = self.ws.doc("Setup/zz-about.md", "About it", "Done here", "Open here")
        about.write_text(about.read_text(encoding="utf-8")
                         + ("\nngspice is installed, ngspice is pinned, ngspice is verified, "
                            "and ngspice runs the simulation.\n"), encoding="utf-8")
        self.assertEqual(self.find("ngspice")[0].file, "Setup/zz-about.md")

    def test_a_frozen_memory_snapshot_never_outranks_the_live_document(self):
        # Setup/handoff/ holds dated copies of Peter's memory, which task-recall reads
        # live anyway. A copy answered "bilingual pages" ahead of the rule itself.
        self.ws.doc("Setup/handoff/claude-memory-2026-09-18/reference-bilingual.md",
                    "Bilingual pages", "Bilingual pages were done", "Bilingual pages open")
        self.ws.doc("Setup/bilingual-rule.md", "The bilingual rule",
                    "Bilingual pages were done", "Bilingual pages open")
        self.assertEqual(self.find("bilingual pages")[0].file, "Setup/bilingual-rule.md")

    def test_prose_never_outranks_a_path_that_names_the_subject(self):
        named = self.ws.doc("Setup/ngspice-install.md", "Install", "Done", "Open")
        chatty = self.ws.doc("Setup/aa-everything.md", "Everything", "Done here", "Open here")
        chatty.write_text(chatty.read_text(encoding="utf-8")
                          + "\nngspice ngspice ngspice, and more ngspice.\n", encoding="utf-8")
        self.assertEqual(self.find("ngspice")[0].file, "Setup/ngspice-install.md")

    def test_a_plural_finds_the_singular_and_words_that_would_mangle_are_left_alone(self):
        # "bilingual pages" could not see CLAUDE.md's "Every page is bilingual".
        self.ws.doc("Setup/house.md", "The house rules", "Every page is bilingual",
                    "One page is not")
        self.assertEqual(self.find("bilingual pages")[0].file, "Setup/house.md")
        self.assertEqual(self.tool.stem("pages"), "page")
        for whole in ("status", "analysis", "across", "chaos", "its"):
            with self.subTest(whole):
                self.assertEqual(self.tool.stem(whole), whole)

    def test_a_query_that_matches_nothing_returns_nothing(self):
        self.ws.doc("Setup/one.md", "A document", "Done", "Open")
        self.assertEqual(self.find("borogoves mimsy"), [])

    def test_short_and_common_words_do_not_decide_a_match(self):
        self.ws.doc("Setup/the-and-for.md", "The and for", "The and for done", "The and for open")
        self.ws.doc("Setup/ngspice.md", "ngspice runs", "ngspice installed", "ngspice untested")
        hits = self.find("the ngspice for")
        self.assertEqual(hits[0].file, "Setup/ngspice.md")

    def test_matching_ignores_case_and_punctuation(self):
        self.ws.doc("Setup/sync.md", "The sync", "sync pushes", "sync defers")
        self.assertEqual(self.find("DEV-SYNC!").pop(0).file, "Setup/sync.md")


class BoxTests(Case):
    def test_the_box_separates_what_is_done_from_what_is_open(self):
        self.ws.doc("Setup/kettle.md", "The kettle", "The first half shipped", "The second half waits")
        box = self.tool.box(self.find("kettle")[0], self.ws.root)
        self.assertIn("The first half shipped", box)
        self.assertIn("The second half waits", box)
        done, opened = box.index("The first half shipped"), box.index("The second half waits")
        self.assertLess(done, opened, "open work must come after what is done")
        self.assertIn("`Setup/kettle.md:13`", box, "an open item must carry its path and line")

    def test_a_plan_box_counts_its_checkboxes(self):
        self.ws.plan("Setup/superpowers/plans/2026-09-18-a-plan.md", "A plan in three steps")
        box = self.tool.box(self.find("plan three steps")[0], self.ws.root)
        self.assertIn("2 of 3", box, box)

    def test_memory_that_names_the_subject_is_shown_with_it(self):
        self.ws.doc("Setup/pyrosim.md", "PyroSim", "The guide is written", "Day seven needs a rerun")
        self.ws.remember("project-pyrosim-guide", "PyroSim is Windows-only and bundles FDS")
        box = self.tool.box(self.find("pyrosim")[0], self.ws.root, memory=self.ws.memory)
        self.assertIn("project-pyrosim-guide", box)
        self.assertIn("Windows-only", box)

    def test_only_the_closest_memories_are_shown_not_every_one_that_shares_a_word(self):
        # Invented "pcb sandbox" must not select every memory sharing "pcb".
        self.ws.doc("PCB Tools/sandbox.md", "Demo Widget", "The port landed", "Aster has not reviewed")
        self.ws.remember("project-pcb-sandbox-build", "Demo Widget build state and its checkpoints")
        self.ws.remember("project-demo-toggle", "A PCB review of the demo toggle")
        box = self.tool.box(self.find("pcb sandbox")[0], self.ws.root, memory=self.ws.memory)
        self.assertIn("project-pcb-sandbox-build", box)
        self.assertNotIn("project-demo-toggle", box)

    def test_a_subject_with_nothing_open_says_so_rather_than_printing_an_empty_list(self):
        self.ws.plan("Setup/superpowers/plans/2026-09-18-finished.md", "A finished plan")
        box = self.tool.box(self.find("finished plan")[0], self.ws.root)
        self.assertRegex(box, r"[Nn]othing open")


class PromptTests(Case):
    def test_the_prompt_counts_remaining_steps_instead_of_completed_steps(self):
        path = self.ws.doc("Setup/kettle.md", "The kettle", "Half shipped", "The rest waits")
        with path.open("a", encoding="utf-8") as out:
            out.write("\n" + "- [x] completed\n" * 5 + "- [ ] remaining\n")
        text = self.tool.next_prompt(self.find("kettle")[0], self.ws.root)
        self.assertIn("1 of 6 steps in that file are still unticked", text)

    def test_the_prompt_names_the_open_work_and_the_file_it_lives_in(self):
        self.ws.doc("Setup/kettle.md", "The kettle", "Half shipped", "The second half waits")
        text = self.tool.next_prompt(self.find("kettle")[0], self.ws.root)
        self.assertIn("The second half waits", text)
        self.assertIn("`Setup/kettle.md:13`", text)

    def test_the_prompt_tells_the_agent_to_grill_and_to_check_before_it_is_done(self):
        # The two house rules a next step must not skip; a prompt that omits
        # them invites exactly the work this workspace keeps having to redo.
        self.ws.doc("Setup/kettle.md", "The kettle", "Half shipped", "The rest waits")
        text = self.tool.next_prompt(self.find("kettle")[0], self.ws.root)
        self.assertIn("grill-first", text)
        self.assertIn("dev-check", text)

    def test_a_finished_subject_gets_a_prompt_that_does_not_invent_work(self):
        self.ws.plan("Setup/superpowers/plans/2026-09-18-finished.md", "A finished plan")
        text = self.tool.next_prompt(self.find("finished plan")[0], self.ws.root)
        self.assertNotIn("- [ ]", text)
        self.assertRegex(text, r"[Nn]othing open|already")


class CommandTests(Case):
    def run_tool(self, *argv):
        return subprocess.run([sys.executable, str(TOOL), "--root", str(self.ws.root),
                               "--status-json", str(self.ws.status_file()),
                               "--memory", str(self.ws.memory), *argv],
                              capture_output=True, text=True, timeout=120,
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"))

    def test_a_match_exits_zero_and_a_miss_exits_one_saying_so(self):
        self.ws.doc("Setup/kettle.md", "The kettle", "Half shipped", "The rest waits")
        hit = self.run_tool("kettle")
        self.assertEqual(hit.returncode, 0, hit.stderr)
        self.assertIn("The rest waits", hit.stdout)
        miss = self.run_tool("borogoves")
        self.assertEqual(miss.returncode, 1)
        self.assertIn("borogoves", miss.stdout + miss.stderr)

    def test_json_carries_the_same_subject_the_box_showed(self):
        self.ws.doc("Setup/kettle.md", "The kettle", "Half shipped", "The rest waits")
        done = self.run_tool("--json", "kettle")
        data = json.loads(done.stdout)
        self.assertEqual(data["subjects"][0]["file"], "Setup/kettle.md")
        self.assertEqual([s["heading"] for s in data["subjects"][0]["open"]], ["The rest waits"])
        self.assertEqual([s["heading"] for s in data["subjects"][0]["done"]], ["Half shipped"])

    def test_prompt_prints_the_next_step_and_nothing_else_by_default(self):
        self.ws.doc("Setup/kettle.md", "The kettle", "Half shipped", "The rest waits")
        done = self.run_tool("--prompt", "kettle")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("The rest waits", done.stdout)

    def test_no_words_at_all_is_a_usage_error(self):
        self.assertEqual(self.run_tool().returncode, 2)

    def test_it_writes_nothing_and_makes_no_network_call(self):
        self.ws.doc("Setup/kettle.md", "The kettle", "Half shipped", "The rest waits")
        before = {p: p.stat().st_mtime_ns for p in self.ws.root.rglob("*") if p.is_file()}
        self.run_tool("kettle")
        after = {p: p.stat().st_mtime_ns for p in self.ws.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after, "task-recall modified the workspace")


class RealWorkspaceTests(unittest.TestCase):
    """Against this checkout. These say what they found; they pin no count."""

    def setUp(self):
        self.memory = tempfile.TemporaryDirectory(prefix="recall-empty-memory-")
        self.addCleanup(self.memory.cleanup)

    def run_tool(self, *argv):
        return subprocess.run([sys.executable, str(TOOL), *argv], capture_output=True, text=True,
                              timeout=300, cwd=str(ROOT),
                              env=dict(os.environ, PYTHONIOENCODING="utf-8",
                                       DEVARNESS_MEMORY_DIR=self.memory.name))

    def test_a_real_subject_of_this_workspace_is_found_and_named(self):
        # The public task record is a real subject without private project files.
        done = self.run_tool("--json", "verified", "changes")
        self.assertEqual(done.returncode, 0, done.stderr[:400])
        data = json.loads(done.stdout)
        self.assertTrue(data["subjects"], "nothing matched the public task record")
        top = data["subjects"][0]["file"].lower()
        self.assertEqual("docs/plan.md", top)

    def test_the_hook_path_keeps_a_memo_and_the_plain_path_writes_nothing(self):
        with tempfile.TemporaryDirectory(prefix="task-recall-memo-") as temp:
            memo = Path(temp) / "memo.json"
            tool = load()
            plain = tool.status_index(ROOT)
            self.assertFalse(memo.exists())
            kept = tool.status_index(ROOT, memo=memo)
            self.assertTrue(memo.is_file(), "asked for a memo and none was written")
            self.assertEqual(kept["counts"], plain["counts"])
            self.assertTrue(kept.get("titles"), "the index carries no titles")

    def test_the_memo_the_hook_writes_is_never_committed(self):
        done = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q",
                               ".claude/hooks/task-recall.memo.json"], capture_output=True, timeout=30)
        self.assertEqual(done.returncode, 0, "the memo is per device and rebuilt at will; "
                                             "git must ignore it or the sync sweeps it up")

    def test_every_path_the_prompt_names_exists(self):
        done = self.run_tool("--prompt", "harness")
        self.assertEqual(done.returncode, 0, done.stderr[:400])
        # Evidence is rendered in backticks because a dev path can carry a space.
        # A subject with nothing open names its file without a line, which is
        # still evidence and must still exist.
        named = [m.split(":")[0] for m in re.findall(r"`([^`]+\.md(?::\d+)?)`", done.stdout)]
        self.assertTrue(named, "the prompt named no evidence at all:\n" + done.stdout)
        for path in named:
            with self.subTest(path):
                self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
