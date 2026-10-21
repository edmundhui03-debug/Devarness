#!/usr/bin/env python3
"""Restore or check the optional shared dev task-support skill; no hooks or APIs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


LIBRARY = Path(__file__).resolve().parent
ROOT = LIBRARY.parent
PIN = "24d22f783e57cb73c957848b588c6f651b6f9cd8"
URL = "https://github.com/ayghri/i-have-adhd.git"
UPSTREAM_SHA256 = "938d0e350a0c2b0e2e6c3a9032542e062846d108e0f89dd27c798ba5b436397e"
LICENSE_SHA256 = "8acbb618089b738404f76ac60fca1aaa995d9a87995eddf95f0b777acd7f7d2c"
NAME = "task-support"
SOURCE = LIBRARY / "task-support" / NAME


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(clone, *args):
    return subprocess.check_output(
        ["git", "-C", str(clone), *args], text=True, stderr=subprocess.PIPE,
        timeout=10,
    ).strip()


def source_checks():
    rows = [line.split("\t") for line in (LIBRARY / "repos.txt").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    matches = [row for row in rows if row[0] == "Library/i-have-adhd"]
    if matches != [["Library/i-have-adhd", URL, PIN]]:
        raise ValueError("repos.txt must contain exactly the reviewed task-support URL and pin")
    clone = LIBRARY / "i-have-adhd"
    # Compare paths, not strings: git on Windows reports forward slashes.
    if Path(git(clone, "rev-parse", "--show-toplevel")).resolve() != clone.resolve():
        raise ValueError("Library/i-have-adhd must be its own pristine Git checkout")
    if git(clone, "rev-parse", "HEAD") != PIN:
        raise ValueError("Upstream HEAD differs from reviewed pin; review before updating")
    if git(clone, "remote", "get-url", "origin") != URL:
        raise ValueError("Upstream origin differs from the manifest URL")
    if git(clone, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("Upstream checkout is dirty; preserve and inspect its changes")
    if digest(clone / "skills/i-have-adhd/SKILL.md") != UPSTREAM_SHA256:
        raise ValueError("Upstream skill does not match the reviewed bytes")
    if digest(SOURCE / "LICENSE") != LICENSE_SHA256:
        raise ValueError("Adapter MIT attribution/license is missing or changed")
    if not (SOURCE / "SKILL.md").is_file():
        raise ValueError("Tracked adapter is missing")
    if not (SOURCE / "agents/openai.yaml").is_file():
        raise ValueError("Tracked Codex invocation policy is missing")


def expected_links():
    result = []
    for client in (".agents", ".claude"):
        destination = ROOT / client / "skills" / NAME
        relative = os.path.relpath(SOURCE, destination.parent)
        result.append((destination, relative))
    return result


def link_state(destination, relative):
    if destination.is_symlink():
        if os.readlink(destination) == relative and destination.resolve() == SOURCE:
            return "ready"
        return "conflict"
    if destination.exists():
        return "conflict"
    return "missing"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true", help="Create missing relative skill links")
    mode.add_argument("--check", action="store_true", help="Read-only inventory; no model request")
    args = parser.parse_args()
    source_checks()
    links = expected_links()
    conflicts = [str(path.relative_to(ROOT)) for path, target in links
                 if link_state(path, target) == "conflict"]
    if conflicts:
        raise ValueError("Preserved conflicting destinations: " + ", ".join(conflicts))
    if args.install:
        for destination, relative in links:
            if link_state(destination, relative) == "missing":
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(relative, target_is_directory=True)
    inventory = [{"path": str(path.relative_to(ROOT)), "target": target,
                  "state": link_state(path, target)} for path, target in links]
    ready = all(item["state"] == "ready" for item in inventory)
    print(json.dumps({
        "tool": NAME,
        "state": "prepared" if ready else "missing",
        "upstream_commit": PIN,
        "upstream_clean": True,
        "source": str(SOURCE.relative_to(ROOT)),
        "adapter_sha256": digest(SOURCE / "SKILL.md"),
        "links": inventory,
        "scope": "explicit skill invocation; no hooks, services, or model requests",
        "note": "File inventory only; client discovery and response quality require separate evidence.",
    }, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("Task support setup refused: " + str(error), file=sys.stderr)
        sys.exit(1)
