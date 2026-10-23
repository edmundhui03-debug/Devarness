#!/usr/bin/env python3
"""Tests for prompt-start.py, the UserPromptSubmit hook that puts grill-first before
and retro-last after every prompt in dev, with the library's picks between them.

Run: python .claude/hooks/test_prompt_start.py

Most tests copy the hook into a throwaway dev tree whose Harness/bin/library is
a stand-in: it logs its arguments and prints, fails, hangs or floods as each
test asks. One test times the real hook on this checkout.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HOOK = HERE / "prompt-start.py"
BUDGET = 2.5
FAKE_LIBRARY = r'''#!/usr/bin/env python3
import os, sys, time
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
    log.write(repr(sys.argv[1:]) + "\n")
if os.environ.get("FAKE_CWD_LOG"):
    with open(os.environ["FAKE_CWD_LOG"], "w", encoding="utf-8") as log:
        log.write(os.getcwd())
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "fail":
    sys.exit(1)
if mode == "slow":
    time.sleep(10)
count = 30 if mode == "many" else 2
for n in range(count):
    print("pick %d: skill:thing-%d  why it fits" % (n, n))
'''

# Matches only "pcb", as a curated label would; anything else gets the generic query.
FAKE_VERCEL = '''GENERIC = "agent skills"
def labels(prompt):  # as the real file: "agent skills" is a label and the fallback
    return [label for label in ("pcb", "agent skills") if label.split()[-1] in prompt]
def keywords(prompt):
    return " ".join(labels(prompt)) or GENERIC
def discover(prompt, root, cwd=None):
    return ["vercel-find [%s]: fake" % keywords(prompt)]
'''


def fire(hook, payload, env=None, cwd=None):
    started = time.monotonic()
    done = subprocess.run([sys.executable, str(hook)], input=payload, capture_output=True, text=True,
                          encoding="utf-8", timeout=60, cwd=str(cwd or ROOT),
                          env=dict(env or os.environ, PYTHONIOENCODING="utf-8"))
    return done, time.monotonic() - started


def event(prompt):
    return json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt, "cwd": str(ROOT)})


class FakeDevTests(unittest.TestCase):
    def test_tieitup_reminder_names_the_loadable_review_owner(self):
        skill = self.root / '.claude/skills/tieitup/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('fixture', encoding='utf-8')
        done, _ = self.run_hook('review the saved JSON contract')
        context = '\n'.join(self.context(done))
        self.assertIn('load .claude/skills/tieitup/SKILL.md', context)
        self.assertIn('pstack review', context)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.hook = self.root / ".claude" / "hooks" / "prompt-start.py"
        self.hook.parent.mkdir(parents=True)
        shutil.copy2(str(HOOK), str(self.hook))
        self.library = self.root / "Harness" / "bin" / "library"
        self.library.parent.mkdir(parents=True)
        self.library.write_text(FAKE_LIBRARY, encoding="utf-8")
        self.log = self.root / "fake.log"

    def run_hook(self, prompt, mode="ok"):
        env = dict(os.environ, FAKE_LOG=str(self.log), FAKE_MODE=mode)
        done, seconds = fire(self.hook, event(prompt), env, cwd=self.root)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done, seconds

    def context(self, done):
        self.assertTrue(done.stdout.strip(), "the hook said nothing")
        output = json.loads(done.stdout)          # stdout is the hook JSON and nothing else
        hook = output["hookSpecificOutput"]
        self.assertEqual(hook["hookEventName"], "UserPromptSubmit")
        self.assertNotIn("decision", output)      # it never blocks
        return hook["additionalContext"].splitlines()

    def calls(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_grill_first_comes_first_the_picks_between_and_retro_last_last(self):
        done, _ = self.run_hook("add a dark mode toggle to the statusline preview")
        lines = self.context(done)
        self.assertTrue(lines[0].startswith("grill-first:"), lines)
        self.assertIn("skill grill-first", lines[0])
        self.assertTrue(lines[-1].startswith("retro-last:"), lines)
        self.assertIn("skill retro-last", lines[-1])
        self.assertTrue(any("pick 0: skill:thing-0" in line for line in lines), lines)
        self.assertEqual(self.calls(), [repr(["pick", "add a dark mode toggle to the statusline preview",
                                              "--top", "3", "--no-path"])])

    def test_the_karpathy_card_is_always_on_after_grill_first(self):
        for prompt in ("fix the typo", "add a dark mode toggle to the statusline preview"):
            lines = self.context(self.run_hook(prompt)[0])
            self.assertTrue(lines[1].startswith("karpathy-guidelines:"), lines)
            self.assertIn("skill karpathy-guidelines", lines[1])

    def test_the_coding_line_names_tieitup_or_falls_back_to_ponytail(self):
        lines = self.context(self.run_hook("fix the typo")[0])
        self.assertIn("load .claude/skills/ponytail/SKILL.md", lines[1])
        skill = self.root / ".claude" / "skills" / "tieitup" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("fixture", encoding="utf-8")
        lines = self.context(self.run_hook("fix the typo")[0])
        self.assertTrue(lines[1].startswith("karpathy-guidelines:"), lines)
        self.assertIn("Ponytail first", lines[1])
        self.assertIn("tieitup check", lines[1])

    def test_the_picks_follow_the_folder_the_prompt_was_typed_in(self):
        # A project's scope applies only when pick runs in the project's folder.
        project = self.root / "Research" / "case"
        project.mkdir(parents=True)
        where = self.root / "cwd.log"
        env = dict(os.environ, FAKE_LOG=str(self.log), FAKE_CWD_LOG=str(where))
        for cwd, expected in ((str(project), project), (str(self.root / "gone"), self.root), (None, self.root)):
            with self.subTest(cwd=cwd):
                payload = {"hook_event_name": "UserPromptSubmit", "prompt": "review the citations in this paper"}
                if cwd:
                    payload["cwd"] = cwd
                done, _ = fire(self.hook, json.dumps(payload), env, cwd=self.root)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(Path(where.read_text(encoding="utf-8")).resolve(), expected.resolve())

    def test_a_cantonese_prompt_reaches_the_library_intact(self):
        prompt = "幫我 整理 呢份 文件 嘅 目錄"
        done, _ = self.run_hook(prompt)
        self.assertEqual(len(self.context(done)), 5)
        self.assertEqual(self.calls(), [repr(["pick", prompt, "--top", "3", "--no-path"])])

    def test_a_prompt_under_four_words_gets_the_gates_and_no_picks(self):
        done, _ = self.run_hook("fix the typo")
        lines = self.context(done)
        self.assertEqual(len(lines), 3, lines)
        self.assertEqual(self.calls(), [])

    def test_a_library_without_pick_or_failing_leaves_the_gates(self):
        done, _ = self.run_hook("which tool converts a scanned PDF to text", mode="fail")
        self.assertEqual(len(self.context(done)), 3)
        self.library.unlink()
        done, _ = self.run_hook("which tool converts a scanned PDF to text")
        self.assertEqual(len(self.context(done)), 3)

    def test_a_slow_library_is_dropped_inside_the_budget(self):
        done, seconds = self.run_hook("which tool converts a scanned PDF to text", mode="slow")
        self.assertLess(seconds, BUDGET + 0.5)     # the interpreter's own start is outside the hook's clock
        self.assertEqual(len(self.context(done)), 3)

    def test_it_says_at_most_twelve_lines_however_much_the_library_prints(self):
        done, _ = self.run_hook("which tool converts a scanned PDF to text", mode="many")
        lines = self.context(done)
        self.assertLessEqual(len(lines), 12)
        self.assertTrue(lines[-1].startswith("retro-last:"))

    def test_vercel_find_runs_only_for_a_curated_keyword(self):
        (self.root / "Harness" / "vercel_find.py").write_text(FAKE_VERCEL, encoding="utf-8")
        unmatched = self.context(self.run_hook("which tool owns fire simulation work here")[0])
        self.assertFalse([line for line in unmatched if line.startswith("vercel-find")])
        matched = self.context(self.run_hook("which tool reviews a pcb layout here")[0])
        self.assertIn("vercel-find [pcb]: fake", matched)
        asked = self.context(self.run_hook("find skills that review a layout here")[0])
        self.assertIn("vercel-find [agent skills]: fake", asked)

    def test_anything_it_cannot_read_costs_nothing(self):
        for payload in ("not json", "[]", json.dumps({"hook_event_name": "Stop"}),
                        json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": 42})):
            done, _ = fire(self.hook, payload, dict(os.environ, FAKE_LOG=str(self.log)), cwd=self.root)
            self.assertEqual(done.returncode, 0, payload)
            self.assertEqual(done.stdout, "", payload)


class ThisCheckoutTests(unittest.TestCase):
    def test_the_real_hook_answers_inside_the_budget(self):
        done, seconds = fire(HOOK, event("which tool converts a scanned PDF to Markdown with pages"))
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"].splitlines()
        self.assertTrue(lines[0].startswith("grill-first:") and lines[-1].startswith("retro-last:"), lines)
        self.assertLessEqual(len(lines), 12)
        self.assertLess(seconds, 7.5, "%.2f s" % seconds)

    def test_settings_run_it_beside_task_recall_on_every_prompt(self):
        settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        commands = [hook["command"] for entry in settings["hooks"]["UserPromptSubmit"]
                    for hook in entry["hooks"]]
        self.assertIn('"$CLAUDE_PROJECT_DIR"/.claude/hooks/prompt-start.sh', commands)
        self.assertIn('"$CLAUDE_PROJECT_DIR"/.claude/hooks/prompt-task-recall.sh', commands)

    @unittest.skipUnless(shutil.which("bash"), "bash is required")
    def test_the_shell_wrapper_hands_the_event_to_the_hook(self):
        done = subprocess.run([shutil.which("bash"), str(HERE / "prompt-start.sh")], input=event("fix it"),
                              capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=str(ROOT))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("grill-first:", json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
