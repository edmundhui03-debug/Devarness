#!/usr/bin/env python3
"""Install the active skill surface for Codex without changing hook trust.

Uses superpowers' upstream at the commit Claude installed and four skills
from the pinned Matt Pocock clone at Harness/skills. ECC stays library-only.
Run after bootstrap/tools installation on each machine. Never overwrites a
different skill, changes model settings, or reconciles Git.
Marketplace add failures stop setup without removing existing registrations.
Resolve source conflicts explicitly before rerunning setup.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
POCOCK = ("productivity/grill-me", "productivity/grilling", "engineering/retro",
          "productivity/writing-for-agents")
REGISTRY = Path.home() / ".claude/plugins/installed_plugins.json"
ERROR_DETAIL_LIMIT = 300


def registered(key):
    """Claude's registry entries for one plugin; none when it has no registry."""
    try:
        return json.loads(REGISTRY.read_text()).get("plugins", {}).get(key) or []
    except (OSError, ValueError):
        return []


def claude_commit(key):
    for e in registered(key):
        if e.get("gitCommitSha"):
            return e["gitCommitSha"]
    raise SystemExit("Claude's plugin registry records no commit for " + key)


def link(source, destination):
    if not (source / "SKILL.md").is_file():
        raise SystemExit("Missing skill: " + str(source))
    if destination.exists() or destination.is_symlink():
        if destination.resolve() != source.resolve():
            raise SystemExit("Refusing to overwrite existing skill: " + str(destination))
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(os.path.relpath(source, destination.parent), target_is_directory=True)


def main():
    # Use the same upstream revision for Claude and Codex.
    superpowers = ["https://github.com/obra/superpowers.git",
                   "--ref", claude_commit("superpowers@claude-plugins-official")]
    failed = []
    for source, selector in ((superpowers, "superpowers@superpowers-dev"),):
        # which() finds codex.cmd on Windows, where a bare name cannot start it.
        codex = shutil.which("codex") or "codex"
        added = subprocess.run([codex, "plugin", "marketplace", "add", *source, "--json"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        if added.returncode != 0:
            # An add failure does not establish that an existing source is stale.
            raise SystemExit("codex-setup: could not add marketplace for %s: %s" % (
                selector, (added.stderr or added.stdout).strip()[-ERROR_DETAIL_LIMIT:]))
        added = subprocess.run([codex, "plugin", "add", selector, "--json"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        if added.returncode != 0:
            # The copy Codex already installed stays in use; finish the rest,
            # then exit non-zero so update-tools names what failed.
            failed.append("could not add %s: %s" % (selector, (added.stderr or added.stdout).strip()[-ERROR_DETAIL_LIMIT:]))
    utilities = ("markitdown", "prompt-master", "bilingual-page", "grill-first", "delegate", "retro-last",
                 "library-intake", "library")
    for name in utilities:
        link(ROOT / ".claude/skills" / name, ROOT / ".agents/skills" / name)
    # Shared Pocock skills support grill-first and retro-last; retro also
    # loads writing-for-agents. Both clients use the same pinned source.
    pocock = ROOT / "Harness/skills/skills"
    for skill in POCOCK:
        link(pocock / skill, ROOT / ".agents/skills" / Path(skill).name)

    print("Installed Codex plugins, {} utility skills and {} Pocock skills.".format(len(utilities), len(POCOCK)))
    print("Restart Codex to load the compact library surface. Hook trust was not changed.")
    if failed:
        # Everything else is done; the exit is so update-tools names what is not.
        raise SystemExit("codex-setup: " + "; ".join(failed))


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    main()
