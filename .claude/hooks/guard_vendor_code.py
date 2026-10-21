#!/usr/bin/env python3
r"""PreToolUse guard: do not download or read a vendor application's packaged code.

On 2026-09-22 a research sub-agent (claude-fable-5-1, general-purpose) was sent
to verify Obsidian facts, read-only, from named public sources. Two questions
asked for settings the docs do not publish, so it fetched Obsidian's update
bundle (`obsidian-1.13.7.asar.gz`), unpacked it and read the minified code to
find the key names. Obsidian's terms forbid that ("disassemble, reverse
engineer or decompile … or otherwise attempt to discover the source code,
object code or underlying structure"). It stopped when it read the terms,
withdrew every claim that rested on the code, and disclosed it — but the brief
should never have let it get there, and the next agent may not stop.

This blocks the class of action, not that one product: fetching or reading a
desktop application's shipped archive — Electron's `.asar`, an app bundle's
`.app`/`.exe`/`.dmg` internals — where the aim can only be to read code that
was not published as source. A key name a vendor does not document is obtained
the legitimate way: set the option in the real application and read the config
file it writes into the owner's own data, which this guard leaves alone.

Exit 2 blocks the call and shows stderr to the agent, main or sub — verified on
2026-09-22 that a PreToolUse guard fires for a general-purpose sub-agent's Bash
call. Anything this cannot read or decide exits 0: a guard that stops ordinary
work gets switched off, and then it guards nothing. Why: Claude/REMINDERS.md,
"A research brief names what is forbidden".
"""
import json
import re
import sys

#: An Electron app archive by name: app.asar, obsidian.asar, foo.asar.gz, .asar.unpacked.
#: There is no legitimate reason to fetch or open one, so this blocks on its own.
ASAR = re.compile(r"(?<![A-Za-z0-9])[\w.-]*\.asar(?:\.unpacked|\.gz|\.br)?(?![A-Za-z0-9])", re.I)
#: A packaged desktop application's innards, or an installer's.
PACKAGE = re.compile(r"\.app/Contents/|\.(?:exe|msi|dmg|pkg|appimage)(?![A-Za-z0-9])", re.I)
#: Prising something open or reading it as code. Installing is none of these:
#: `cp -R Obsidian.app /Applications/` and `hdiutil attach` move a bundle about
#: without looking inside it, and the first guard wrongly refused both, which
#: would have blocked the trial's own first step (found by running it).
INSPECT = re.compile(r"(?<![A-Za-z0-9])(?:strings|xxd|hexdump|od|nm|otool|objdump|class-dump"
                     r"|jadx|apktool|unzip|7z|asar|decompile|disassemble)(?![A-Za-z0-9])", re.I)

ADVICE = ("Reading a vendor application's shipped code is out of scope and a vendor's terms "
          "usually forbid it (this rule exists because claude-fable-5-1 unpacked Obsidian's "
          ".asar on 2026-09-22). A setting a vendor does not document is `not checked` until "
          "you get it the legitimate way: install the real application, set the option in its "
          "settings, and read the config file it writes into the owner's own data. Ask the "
          "owner before touching the application's own package. Why: Claude/REMINDERS.md, "
          "\"A research brief names what is forbidden\".")


#: Commands that move text about and cannot open a package. A message, a
#: search or a log line may name an archive; naming one is not reading it, and
#: a guard that stops you writing about itself is a defect (2026-09-22: this
#: blocked the commit that fixed it). Evasion is covered by judging each
#: segment on its own, so `git log && curl …asar` is still refused.
TEXT_ONLY = re.compile(r"^\s*(?:sudo\s+)?(?:git|echo|printf)(?![A-Za-z0-9_-])", re.I)
#: Where one command ends and the next begins, on a line that is not heredoc body.
SEPARATOR = re.compile(r"&&|\|\||[;|]")
#: `<<EOF`, `<< "EOF"`, `<<-'EOF'`: the opener and the delimiter it waits for.
OPENER = re.compile(r"<<-?\s*(?:(['\"])([^'\"]+)\1|([A-Za-z_][A-Za-z0-9_]*))")


def segments(command):
    """The command split into the parts a shell would run separately.

    A heredoc body stays with the command that opened it, so `git commit -F -`
    keeps its message and `python3 - <<EOF` keeps the code that reads a file.
    """
    parts, current, waiting = [], [], []
    for line in command.split("\n"):
        if waiting:                              # inside a body: it is all one command's
            current.append(line)
            if line.strip() == waiting[0]:
                waiting = waiting[1:]
            continue
        pieces = SEPARATOR.split(line)
        current.append(pieces[0])
        for piece in pieces[1:]:
            parts.append("\n".join(current))
            current = [piece]
        waiting = [m.group(2) or m.group(3) for m in OPENER.finditer(line)]
    parts.append("\n".join(current))
    return [part for part in parts if part.strip()]


def _text(tool, given):
    if tool in ("Bash", "PowerShell"):
        value = given.get("command")
    elif tool == "WebFetch":
        value = given.get("url")
    else:
        return None
    return value if isinstance(value, str) else None


def verdict(tool, given):
    """The sentence that refuses this call, or None when it is fine."""
    if not isinstance(given, dict):
        return None
    text = _text(tool, given)
    if not text:
        return None
    parts = segments(text) if tool in ("Bash", "PowerShell") else [text]
    for part in parts:
        if TEXT_ONLY.match(part):
            continue
        hit = ASAR.search(part)
        if not hit:
            # A package on its own is one to install; it is refused only when
            # the same command also prises it open or reads it as code.
            package, inspect = PACKAGE.search(part), INSPECT.search(part)
            if not (package and inspect):
                continue
            hit = package
        return ("Blocked: this reads a vendor application's packaged code ("
                + hit.group(0) + "). " + ADVICE)
    return None


def main():
    try:
        event = json.load(sys.stdin)
        tool = event.get("tool_name")
        given = event.get("tool_input")
    except (ValueError, AttributeError, OSError):
        return 0
    refusal = verdict(tool, given) if isinstance(tool, str) else None
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
