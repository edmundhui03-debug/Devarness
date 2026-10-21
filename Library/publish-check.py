#!/usr/bin/env python3
"""publish-check: dev's files carry no personal value, so dev could be published.

Usage: python Library/publish-check.py [ROOT]

Reads every file git tracks under ROOT, and every untracked one it would add
(default: the repository holding this script), and prints path:line and the
kind of each hit, never the value: a home path naming a user (C:/Users/<name>,
/Users/<name>, /home/<name>; placeholders such as <user>, %USERPROFILE% and $USER
pass), an identifier from ~/.config/devarness/identifiers.txt (one per line: the
owner's email, accounts, real name), the ntfy topic (~/.config/devarness/ntfy-topic or
DEVARNESS_NTFY_TOPIC), an email address that is not an example or a noreply address,
and the third-party book repository's name. With no identifiers file the
generic checks still run, and it says so.

The build records (Setup/superpowers/, Setup/AGENT_LEDGER.md and each project's
PRDs and Specs/<project>/evidence/) are exempt but
listed as warnings, so the owner sees what publishing them would expose. The
history files (LESSONS.md, CHANGES.md) are checked like any other: the old
workspace's commit hashes they cite are not personal values. Exits 1 when a
file that is not exempt has a hit. Standard library only.
"""
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

EXEMPT = ("Setup/superpowers/", "Setup/AGENT_LEDGER.md")
# A project's evidence/ folder under PRDs and Specs/ is a build record too (owner, 2026-10-16).
EVIDENCE = re.compile(r"PRDs and Specs/[^/]+/evidence/")
# C:\Users\<name>, C:/Users/<name>, MSYS's /c/Users/<name>, /Users/<name> and /home/<name>.
HOME_PATH = re.compile(r"(?<![\w.~-])(?:[A-Za-z]:|/[A-Za-z](?=/))?[\\/]+(?:Users|home)[\\/]+([^\\/\s\"'`)<>|,;]+)",
                       re.IGNORECASE)
# A variable, a regex class or a word any machine could have; node is a container's own user.
PLACEHOLDER = re.compile(r"^(?:[<%${*.\[]|(?:user|username|you|yourname|name|me|someone|owner|example|public|"
                         r"shared|default|runner|node)$)", re.IGNORECASE)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")
EXAMPLE = re.compile(r"(?:^|\.)(?:example\.(?:com|org|net)|[a-z0-9-]+\.(?:example|invalid|test|localhost))$",
                     re.IGNORECASE)
BOOKS = "some-" "many-books"            # split so this file does not carry the name it looks for


def personal_values(config):
    """(identifiers, topic, note): what the owner keeps in ~/.config/devarness; note says what is missing."""
    path = config / "identifiers.txt"
    identifiers, note = [], ""
    if path.is_file():
        identifiers = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                       if line.strip() and not line.startswith("#")]
    else:
        note = "publish-check: no ~/.config/devarness/identifiers.txt; generic checks only"
    topic = os.environ.get("DEVARNESS_NTFY_TOPIC", "").strip()
    if not topic and (config / "ntfy-topic").is_file():
        topic = (config / "ntfy-topic").read_text(encoding="utf-8").strip()
    return identifiers, topic, note


def hits(line, identifiers, topic):
    """The kinds of personal value on one line; never the values themselves."""
    lower = line.lower()
    found = []
    if any(not PLACEHOLDER.match(m.group(1)) for m in HOME_PATH.finditer(line)):
        found.append("home path naming a user")
    if any(value.lower() in lower for value in identifiers):
        found.append("personal identifier")
    if topic and topic.lower() in lower:
        found.append("ntfy topic")
    for match in EMAIL.finditer(line):
        local = match.group(0).split("@")[0].lower()
        if not (EXAMPLE.search(match.group(1)) or "noreply" in match.group(0).lower()
                or "no-reply" in local or local == "git"):
            found.append("email address")
            break
    if BOOKS in lower:
        found.append("third-party book repository")
    return found


def files(root):
    listing = common.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         capture_output=True, check=True, timeout=120).stdout
    return sorted({name for name in listing.decode("utf-8").split("\0") if name})


def scan(root, identifiers, topic):
    """Each hit as (exempt, 'path:line: kinds')."""
    report = []
    for name in files(root):
        exempt = name.startswith(EXEMPT) or bool(EVIDENCE.match(name))
        for kind in hits(name, identifiers, topic):
            report.append((exempt, "%s:0: %s (the file name)" % (name, kind)))
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            kinds = hits(line, identifiers, topic)
            if kinds:
                report.append((exempt, "%s:%d: %s" % (name, number, ", ".join(kinds))))
    return report


def main(argv):
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    identifiers, topic, note = personal_values(common.config_dir())
    if note:
        print(note)
    report = scan(root, identifiers, topic)
    for exempt, entry in report:
        print(("warning: %s (a build record, exempt)" % entry) if exempt else entry)
    failing = [entry for exempt, entry in report if not exempt]
    warned = len(report) - len(failing)
    print("publish-check: %d hit(s) in %d file(s); %d warning(s) in build records"
          % (len(failing), len({e.split(":", 1)[0] for e in failing}), warned) if failing
          else "publish-check: clean; %d warning(s) in build records" % warned)
    return 1 if failing else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    sys.exit(main(sys.argv))
