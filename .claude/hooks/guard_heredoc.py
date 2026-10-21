#!/usr/bin/env python3
r"""PreToolUse guard: on Windows, no backslash inside a Bash heredoc.

The Bash tool rewrites a heredoc's body on this PC before bash sees it: `\\`
arrives as `\`, `\"` as `"`. Python then reads what is left as an escape, so
`'\\n'` becomes a real newline. It corrupted a project CLAUDE.md on
2026-09-17 and broke seven commands on 2026-09-19, each time with the rule
already written in Claude/REMINDERS.md; a note read at session start is not
in view when a heredoc is being typed. This is that rule, enforced.

The way through is the Write or Edit tool, which passes bytes unchanged, or
building the backslash at run time with chr(92).

Only Windows blocks: the Mac's Bash tool passes a heredoc through as typed.
Exit 2 blocks the tool call and shows stderr to the agent. Anything this
cannot read or decide exits 0: a guard that stops ordinary work gets
switched off, and then it guards nothing.
"""
import json
import re
import sys

#: `<<EOF`, `<< "EOF"`, `<<-'EOF'`: the opener and the delimiter it waits for.
OPENER = re.compile(r"<<-?\s*(?:(['\"])([^'\"]+)\1|([A-Za-z_][A-Za-z0-9_]*))")
ADVICE = ("A heredoc here loses its backslashes: the Bash tool rewrites the body before bash "
          "sees it, so \\\\ arrives as \\ and \\\" as \". Write the file with the Write or Edit "
          "tool, which passes bytes unchanged, or build the backslash at run time with chr(92). "
          "Why: Claude/REMINDERS.md, \"On Windows the Bash tool's heredoc collapses a double "
          "backslash\".")


def heredoc_bodies(command):
    """Every heredoc body in this command, in order, as one string each."""
    lines, bodies = command.splitlines(), []
    waiting, body = [], []
    for line in lines:
        if waiting:
            if line.strip() == waiting[0]:
                bodies.append("\n".join(body))
                body, waiting = [], waiting[1:]
            else:
                body.append(line)
            continue
        # A line may open more than one: `sort <<A <<B`. Each waits in turn.
        waiting = [match.group(2) or match.group(3) for match in OPENER.finditer(line)]
    if waiting:                                  # never terminated: the rest is body
        bodies.append("\n".join(body))
    return bodies


def verdict(command, platform=sys.platform):
    """None when the command is fine, else the sentence that says why not."""
    if platform != "win32" or not isinstance(command, str) or "<<" not in command:
        return None
    for body in heredoc_bodies(command):
        if "\\" in body:
            line = next(one for one in body.splitlines() if "\\" in one)
            return "A backslash in a heredoc: " + line.strip()[:120] + ". " + ADVICE
    return None


def main():
    try:
        event = json.load(sys.stdin)
        command = (event.get("tool_input") or {}).get("command")
    except (ValueError, AttributeError, OSError):
        return 0
    refusal = verdict(command)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
