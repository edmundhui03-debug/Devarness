#!/usr/bin/env python3
"""UserPromptSubmit hook: when a prompt names something dev is tracking, put its state in front.

The owner asked for a tool that remembers as soon as a project is mentioned,
rather than one that has to be invoked. A router rule would depend on whichever
agent is reading it; this does not — the harness runs it on the prompt itself
and hands the answer back as additionalContext, before the model reads a thing.

It adds, it never blocks. A UserPromptSubmit hook *can* refuse a turn, and this
one must not: the workspace already refused one always-on gate on the grounds that it would
argue on every turn (CLAUDE.md, the claude-scholar boundary). The rule here is
narrower — say something only when the prompt names what dev tracks, say it in at
most a dozen lines, and say nothing at all otherwise.

Anything it cannot read or decide exits 0 with no output: a hook that breaks
ordinary prompting gets switched off, and then it recalls nothing.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "Library" / "bin" / "task-recall"
# The gate is task-recall's, asked for with --named: it answers only when the prompt
# NAMES a subject — two words said together and found together in one name. No
# total and no count decides it here. A total let "can you fix the typo" reach 4.9
# on a Example App handover; a count of shared words, which replaced it, let "test",
# "rest" and "bugs" each speak the day the documents tripled (2026-09-22).
OPEN_SHOWN = 4
BOUND = 20
# A prompt that is already about the tool, or is answering it, needs no recall.
SKIP = ("task-recall", "/clear", "/compact")
# The harness hands this hook a finished background task as if it were a prompt.
# Nobody typed it, and a page of machine-written text shares a word with
# everything: on 2026-09-22 one put a Example App record into a turn the owner
# never wrote.
NOT_THE_OWNER = ("<task-notification>", "[SYSTEM NOTIFICATION")


def recall(prompt: str):
    argv = [sys.executable, str(TASK), "--json", "--named", "--quiet", "--", prompt]
    try:
        done = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=BOUND, stdin=subprocess.DEVNULL,
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0 or not done.stdout.strip():
        return None
    try:
        subjects = json.loads(done.stdout).get("subjects") or []
    except ValueError:
        return None
    return subjects[0] if subjects else None


def context(subject) -> str:
    """At most a dozen lines: what it is, what is open, and how to ask for more."""
    lines = ["dev is tracking this. From its own records, not from memory:",
             "  %s — `%s`" % (subject.get("title") or subject["file"], subject["file"])]
    boxes = subject.get("checkboxes")
    if boxes:
        lines.append("  %d of %d steps ticked" % tuple(boxes))
    done, still = subject.get("done") or [], subject.get("open") or []
    if done:
        lines.append("  %d section%s already closed there" % (len(done), "" if len(done) == 1 else "s"))
    if still:
        lines.append("  still open:")
        for item in still[:OPEN_SHOWN]:
            lines.append("    - [%s] %s — `%s:%d`"
                         % (item["status"], item["heading"], subject["file"], item["line"]))
        if len(still) > OPEN_SHOWN:
            lines.append("    ... %d more" % (len(still) - OPEN_SHOWN))
    else:
        lines.append("  nothing open there")
    for memory in (subject.get("memories") or [])[:2]:
        lines.append("  memory: %s" % memory["name"])
    lines.append("  Read the files before acting on this summary; "
                 "`task-recall --prompt` gives the next step in full.")
    return "\n".join(lines)


def main():
    try:
        event = json.load(sys.stdin)
        if event.get("hook_event_name", "UserPromptSubmit") != "UserPromptSubmit":
            return
        prompt = event.get("prompt")
    except (ValueError, OSError, AttributeError):
        return
    if not isinstance(prompt, str) or len(prompt.strip()) < 4:
        return
    if any(mark in prompt.lower() for mark in SKIP):
        return
    if any(mark in prompt for mark in NOT_THE_OWNER):
        return
    if not TASK.is_file():
        return
    subject = recall(prompt)
    if not subject:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": context(subject)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:          # never let recall cost the owner a turn
        pass
    sys.exit(0)
