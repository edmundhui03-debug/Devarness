#!/usr/bin/env python3
"""PreToolUse guard: no `git commit --amend` in the middle of a rebase, unless git stopped for one.

On 2026-09-17 a failed `git rebase --continue`, hidden behind a pipe, was followed by
`git commit --amend`. HEAD was still the other device's newest commit, so the amend folded it
into this device's. Git itself marks the one moment an amend is right during a rebase by writing
HEAD into `rebase-merge/amend`; this allows exactly that and blocks the rest.

Exit 2 blocks the tool call and shows stderr to the agent. Anything this cannot read or decide
exits 0: a guard that breaks ordinary work gets switched off, and then it guards nothing.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

AMEND = re.compile(r"\bgit\b[^|;&\n]*\bcommit\b[^|;&\n]*--amend\b")


def git(repo, *args):
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=5)
    if done.returncode:
        raise OSError(done.stderr)
    return done.stdout.strip()


def repositories(command, cwd):
    """Where the amend would run: `git -C DIR`, else a leading `cd DIR`, else the tool's directory."""
    try:
        # Not POSIX mode: that would eat the backslashes of a Windows path.
        words = [word.strip("'" + '"') for word in shlex.split(command, posix=False)]
    except ValueError:
        words = command.split()
    found = [words[i + 1] for i, word in enumerate(words[:-1]) if word == "-C" and i and words[i - 1] == "git"]
    if not found:
        found = [words[i + 1] for i, word in enumerate(words[:-1]) if word in ("cd", "Set-Location", "pushd")][:1]
    # Git's bash on Windows writes C:/Users as /c/Users, which Python would read as a folder named c.
    found = [re.sub(r"^/([A-Za-z])/", r"\1:/", place) if sys.platform == "win32" else place for place in found]
    return [Path(cwd, place) for place in found] or [Path(cwd)]


def verdict(repo):
    """None when the amend is fine here, else the sentence that says why not."""
    try:
        git_dir = Path(git(repo, "rev-parse", "--absolute-git-dir"))
        head = git(repo, "rev-parse", "HEAD")
        subject = git(repo, "log", "-1", "--format=%h %s")
    except (OSError, subprocess.SubprocessError):
        return None
    if (git_dir / "rebase-apply").exists():
        return "a rebase is in progress in {}".format(repo)
    if not (git_dir / "rebase-merge").exists():
        return None
    try:
        if (git_dir / "rebase-merge" / "amend").read_text().strip() == head:
            return None
    except OSError:
        pass
    return ("a rebase is stopped in {} and git did not stop it for an amend. HEAD is '{}', which is not "
            "your commit: amending would rewrite it".format(repo, subject))


def main():
    try:
        event = json.load(sys.stdin)
        command = event["tool_input"]["command"]
        if event.get("tool_name") not in ("Bash", "PowerShell") or not AMEND.search(command):
            return 0
        reasons = [reason for reason in map(verdict, repositories(command, event.get("cwd") or ".")) if reason]
    except Exception:       # never let the guard itself stop work
        return 0
    if not reasons:
        return 0
    print("Blocked: {}. Run `git status`, finish with `git rebase --continue` on its own line and read its "
          "result, and reword only once the branch is checked out again.".format("; ".join(reasons)),
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
