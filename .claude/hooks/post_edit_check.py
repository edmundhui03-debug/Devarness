#!/usr/bin/env python3
"""PostToolUse hook: after Edit or Write on a document dev owns, run the house checker on it.

The house format and the bilingual rule depended on the agent remembering to run
`md-format check` or `i18n check` before calling a document done. This runs the
right one on the file that was just changed and hands its findings back into the
session as additionalContext. It never blocks — the edit has already happened —
and it says nothing at all when the file is clean, is not a document, or is not
dev's to check: a vendored clone, a separate project, an ignored path, a
template, or anything outside this checkout.

Anything it cannot read or decide exits 0 with no output: a hook that breaks
ordinary editing gets switched off, and then it checks nothing.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ("Edit", "Write", "MultiEdit")
CHECKERS = {".md": ("Library/bin/md-format", "check"), ".html": ("Library/bin/i18n", "check")}
# Code goes to tieitup, which always exits 0: any line on its stdout is a finding.
TIEITUP = "Library/bin/tieitup"
CODE = {".py", ".sh", ".bash", ".c", ".h", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}
SHEBANGS = ("python", "bash", "sh")
LEFT_ALONE = ("Library/templates/", "/_review/shots/")
LINES = 12
BOUND = 25


def git(*args, cwd):
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=10)
    return done.returncode, done.stdout.strip()


def ours(path: Path):
    """True when the file sits in this checkout, in dev's own repository, and is not ignored."""
    try:
        real = path.resolve()
        root = ROOT.resolve()
        real.relative_to(root)
    except (OSError, ValueError):
        return False
    relative = real.relative_to(root).as_posix()
    if any(mark.strip("/") in ("/" + relative) for mark in LEFT_ALONE):
        return False
    try:
        code, top = git("rev-parse", "--show-toplevel", cwd=real.parent)
        if code or Path(top).resolve() != root:
            return False               # not a git checkout, or a nested repository's file
        code, _ = git("check-ignore", "-q", str(real), cwd=root)
        if code == 0:
            return False               # ignored: generated, per-device, or a clone
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def is_code(path: Path):
    if path.suffix:
        return path.suffix.lower() in CODE
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return False
    words = first[2:].split() if first.startswith("#!") else []
    if words and Path(words[0]).name == "env":
        words = words[1:]
    name = Path(words[0]).name if words else ""
    return name.startswith("python") or name in SHEBANGS


def code_repository(path: Path):
    """The repository tieitup runs in: dev's own for a file dev owns, or a separate
    project's for a file inside one listed in Library/separate-projects.txt."""
    if ours(path):
        return ROOT
    try:
        real = path.resolve()
        relative = real.relative_to(ROOT.resolve()).as_posix()
        listed = (ROOT / "Library/separate-projects.txt").read_text(encoding="utf-8").splitlines()
        code, top = git("rev-parse", "--show-toplevel", cwd=real.parent)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    projects = {line.strip().strip("/") for line in listed if line.strip() and not line.startswith("#")}
    if code or Path(top).resolve().relative_to(ROOT.resolve()).as_posix() not in projects:
        return None
    if not any(relative.startswith(project + "/") for project in projects):
        return None
    code, _ = git("check-ignore", "-q", str(real), cwd=top)
    return None if code == 0 else Path(top)


def code_report(path: Path, repository: Path):
    """tieitup's findings for this file, or None when it says nothing or cannot run."""
    argv = [sys.executable, str(ROOT / TIEITUP), "check", "--", str(path)]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=BOUND, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                              cwd=str(repository), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None    # a fault in the check never reaches the edit
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    if not lines or path.name not in done.stdout:
        return None
    shown = lines[:LINES]
    if len(lines) > LINES:
        shown.append("... %d more lines; run `tieitup check -- %s`" % (len(lines) - LINES, path.name))
    return "tieitup check on %s:\n%s" % (path.name, "\n".join(shown))


def interpreter(launcher: Path):
    try:
        with launcher.open(encoding="utf-8", errors="replace") as fh:
            first = fh.readline()
    except OSError:
        return [str(launcher)]
    if "python" in first:
        return [sys.executable, str(launcher)]
    return ["bash", str(launcher)]


def report(path: Path):
    """The checker's findings for this file, or None when there is nothing to say."""
    launcher, verb = CHECKERS[path.suffix.lower()]
    argv = interpreter(ROOT / launcher) + [verb, str(path)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        done = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=BOUND, env=env, cwd=str(ROOT), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "%s %s: no answer within %ds" % (launcher, verb, BOUND)
    except OSError as error:
        return "%s %s could not run: %s" % (launcher, verb, error)
    output = (done.stdout + done.stderr).strip()
    problems = done.returncode != 0 or (path.suffix.lower() == ".html" and "toggle=NO" in output)
    if not problems:
        return None
    if path.name not in output:
        # The checker failed about itself, not about this file — i18n on a
        # device with no markitdown python says "needs markitdown's python at
        # ...", which would otherwise answer every HTML edit on a new machine.
        return None
    lines = [line for line in output.splitlines() if line.strip()]
    shown = lines[:LINES]
    if len(lines) > LINES:
        shown.append("... %d more lines; run `%s %s %s`" % (len(lines) - LINES, launcher, verb,
                                                            path.relative_to(ROOT.resolve())))
    return "%s %s on %s:\n%s" % (launcher, verb, path.name, "\n".join(shown))


def main():
    try:
        event = json.load(sys.stdin)
        if event.get("hook_event_name", "PostToolUse") != "PostToolUse":
            return
        if event.get("tool_name") not in TOOLS:
            return
        target = event["tool_input"]["file_path"]
    except (ValueError, KeyError, TypeError, OSError):
        return
    path = Path(target)
    if not path.is_absolute():
        path = Path(str(event.get("cwd") or ROOT), target)
    if not path.is_file():
        return
    if path.suffix.lower() in CHECKERS:
        text = report(path.resolve()) if ours(path) else None
    elif (ROOT / TIEITUP).is_file() and is_code(path):
        repository = code_repository(path)
        text = code_report(path.resolve(), repository) if repository else None
    else:
        return
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:            # never let a checker fault fail an edit
        pass
    sys.exit(0)
