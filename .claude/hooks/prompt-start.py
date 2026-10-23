#!/usr/bin/env python3
"""UserPromptSubmit hook: grill-first and the Karpathy card before, retro-last after, the library's picks between.

The owner asked for "grill-first, retro-last for auto running every prompt in
the dev folder". A router rule depends on whichever agent reads it; this runs on
the prompt itself and hands the reminder back as additionalContext before the
model reads anything. It adds and never blocks: everything it cannot read or
decide exits 0 with nothing on stdout, because a hook that breaks ordinary
prompting gets switched off.

The picks are `library pick "<prompt>" --top 3 --no-path`, skipped for a prompt under
four words and dropped when the library is missing, fails or misses the budget.
Vercel find runs when a prompt matches a curated keyword, at most four seconds
and three untrusted candidates. All clients share this implementation.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "Harness" / "bin" / "library"
GRILL = ("grill-first: before non-trivial work, ask every open question at once "
         "with a recommended answer (skill grill-first)")
# The owner keeps the Karpathy coding card always on; the policy's always-on mode alone puts it nowhere.
KARPATHY = ("karpathy-guidelines: think before coding, the simplest change, surgical edits, a verifiable "
            "goal (skill karpathy-guidelines)")
# TieItUp owns how code is written (owner, 2026-10-15); with its skill missing, Ponytail is the fallback.
# It rides on the Karpathy line so the reminder keeps within twelve lines.
TIEITUP = ("; code: load .claude/skills/tieitup/SKILL.md: Ponytail first, book rules, "
           "pstack review, tieitup check before done (skill tieitup)")
PONYTAIL = "; code: load .claude/skills/ponytail/SKILL.md, full mode (skill ponytail)"
RETRO = "retro-last: end the turn with one evidence-based retrospective (skill retro-last)"
PICK_SECONDS = 2.0      # plus at most four seconds for Vercel discovery
MIN_WORDS = 4
# Windows caps a command line near 32k characters; a pasted log needs only its start.
PROMPT_CHARS = 2000


def picks(prompt, cwd):
    if len(prompt.split()) < MIN_WORDS or not LIBRARY.is_file():
        return []
    # pick reads its project, and so the project's scope, from the folder it runs in.
    where = cwd if isinstance(cwd, str) and os.path.isdir(cwd) else str(ROOT)
    try:
        done = subprocess.run([sys.executable, str(LIBRARY), "pick", prompt[:PROMPT_CHARS], "--top", "3", "--no-path"],
                              cwd=where, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=PICK_SECONDS, stdin=subprocess.DEVNULL,
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return [line.rstrip() for line in done.stdout.splitlines() if line.strip()]


def main():
    # Bytes, decoded here: Windows would read a piped stdin in its ANSI code page.
    event = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    if event.get("hook_event_name", "UserPromptSubmit") != "UserPromptSubmit":
        return
    prompt = event["prompt"]
    if not isinstance(prompt, str):
        return
    external = []
    sys.path.insert(0, str(ROOT / 'Harness'))
    try:
        from vercel_find import discover, labels
        if labels(prompt):  # no curated label: the generic search repeats the same three
            external = discover(prompt, ROOT, cwd=event.get('cwd'))
    except ImportError:
        pass  # A minimal/test checkout may carry only the local library.
    except (OSError, ValueError):
        external = ['vercel-find: unavailable; continue with local library picks.']
    coding = TIEITUP if (ROOT / ".claude/skills/tieitup/SKILL.md").is_file() else PONYTAIL
    lines = ([GRILL, KARPATHY + coding] + picks(prompt, event.get("cwd"))[:8]
             + external[:4] + [RETRO])
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                             "additionalContext": "\n".join(lines)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:          # never let the reminder cost the owner a turn
        pass
    sys.exit(0)
