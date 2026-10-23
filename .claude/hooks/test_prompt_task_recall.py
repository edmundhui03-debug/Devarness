#!/usr/bin/env python3
"""Tests for prompt_task_recall.py, the UserPromptSubmit hook that recalls a named task.

The hook must be quiet far more often than it speaks: it runs on every prompt,
and a box dragged into a turn that did not ask for one is worse than no box at
all. These tests pin when it speaks, what it says, and that nothing it cannot
read ever costs the owner a turn.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HOOK = HERE / "prompt_task_recall.py"


def load():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("prompt_task_recall", str(HOOK))
    spec = importlib.util.spec_from_loader("prompt_task_recall", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


SUBJECT = {
    "file": "Setup/superpowers/plans/2026-09-18-a-plan.md",
    "title": "A plan in three steps",
    "score": 6.0,
    "checkboxes": [2, 3],
    "open": [{"status": "open", "heading": "The third step waits", "line": 42},
             {"status": "blocked", "heading": "Aster has not reviewed it", "line": 61}],
    "done": [{"status": "fixed", "heading": "The first two landed", "line": 20}],
    "memories": [{"name": "project-a-plan", "description": "why the plan exists"}],
}


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.hook = load()

    def test_the_box_names_the_file_the_open_work_and_where_it_lives(self):
        text = self.hook.context(SUBJECT)
        self.assertIn("A plan in three steps", text)
        self.assertIn("The third step waits", text)
        self.assertIn("`Setup/superpowers/plans/2026-09-18-a-plan.md:42`", text)
        self.assertIn("2 of 3", text)

    def test_it_stays_within_a_dozen_lines_however_much_is_open(self):
        many = dict(SUBJECT, open=[{"status": "open", "heading": "item %d" % n, "line": n}
                                   for n in range(40)])
        text = self.hook.context(many)
        self.assertLessEqual(len(text.splitlines()), 12, text)
        self.assertIn("more", text)

    def test_it_tells_the_reader_the_summary_is_not_the_evidence(self):
        # The box is a pointer. A session that acts on it without opening the
        # files is the failure this workspace keeps writing rules about.
        self.assertIn("Read the files", self.hook.context(SUBJECT))

    def test_a_subject_with_nothing_open_says_so(self):
        self.assertIn("nothing open", self.hook.context(dict(SUBJECT, open=[])))


class FiringTests(unittest.TestCase):
    def setUp(self):
        self.memory = tempfile.TemporaryDirectory(prefix="recall-empty-memory-")
        self.addCleanup(self.memory.cleanup)

    def fire(self, prompt, raw=None):
        payload = raw if raw is not None else json.dumps(
            {"hook_event_name": "UserPromptSubmit", "prompt": prompt, "cwd": str(ROOT)})
        return subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True,
                              text=True, timeout=120, cwd=str(ROOT),
                              env=dict(os.environ, PYTHONIOENCODING="utf-8",
                                       DEVARNESS_MEMORY_DIR=self.memory.name))

    def said(self, done):
        self.assertEqual(done.returncode, 0, done.stderr)
        if not done.stdout.strip():
            return None
        return json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_a_prompt_naming_a_real_project_gets_its_state(self):
        # The public task record has this pair in its title.
        text = self.said(self.fire("where did we get to with verified changes?"))
        self.assertIsNotNone(text, "the hook said nothing about a project dev is tracking")
        self.assertIn("dev is tracking this", text)

    def test_an_ordinary_prompt_that_names_nothing_is_left_alone(self):
        for prompt in ("hello", "what time is it", "thanks, that looks right",
                       "ok go ahead and do it"):
            with self.subTest(prompt):
                self.assertIsNone(self.said(self.fire(prompt)))

    def test_it_does_not_answer_a_prompt_that_is_already_about_the_tool(self):
        self.assertIsNone(self.said(self.fire("run task-recall pcb sandbox for me")))

    def test_anything_it_cannot_read_never_costs_a_turn(self):
        for raw in ("", "not json", "null", json.dumps({"prompt": None}),
                    json.dumps({"hook_event_name": "PreToolUse", "prompt": "pcb sandbox"}),
                    json.dumps({"prompt": "hi"})):
            with self.subTest(raw[:14]):
                done = self.fire(None, raw=raw)
                self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_a_harness_notification_is_not_the_owner_speaking(self):
        # A finished background task is delivered to this hook as a prompt. The text
        # is long and machine-written, so word overlap alone is insufficient.
        # The quoted project prompt below is an invented example, not user input.
        note = ("<system-reminder>\n[SYSTEM NOTIFICATION - NOT USER INPUT]\n<task-notification>\n"
                "<summary>Agent finished</summary>\n<result>where did we get to with the pcb "
                "sandbox windows port?</result>\n</task-notification>\n</system-reminder>")
        self.assertIsNone(self.said(self.fire(note)))

    def test_one_ordinary_word_that_happens_to_be_in_a_path_names_nothing(self):
        # Common words such as "test", "rest" and "bugs" can occur in unrelated
        # document paths. One shared word must not interrupt ordinary prompts.
        for prompt in ("little test, can still remember what we discussed before?",
                       "nice. Take some rest Example",
                       "fix the bugs and continue improve"):
            with self.subTest(prompt):
                self.assertIsNone(self.said(self.fire(prompt)))

    def test_prose_alone_is_never_enough_to_interrupt_a_turn(self):
        # Generic editing prose can overlap unrelated handovers. The gate is
        # task-recall's own: `--named` answers only when the prompt names a subject,
        # and no aggregate prose score or document count decides it here.
        hook = load()
        self.assertIn('"--named"', Path(hook.__file__).read_text(encoding="utf-8"),
                      "the gate must be task-recall --named, never a score read here")
        for prompt in ("can you fix the typo", "please make that a bit clearer",
                       "what do you think we should do next"):
            with self.subTest(prompt):
                self.assertIsNone(self.said(self.fire(prompt)))


if __name__ == "__main__":
    unittest.main()
