#!/usr/bin/env python3
"""Copy the prompt-master skill from its pinned clone into .claude/skills.

  --install   copy SKILL.md and references/ from the clone
  --check     exit 1 and name each file that differs from the clone

The skill is copied rather than linked because the copy must survive a
re-clone and a device without the symlink privilege. The clone keeps the
skill either under skills/prompt-master or at its root; both are looked
for. DEVARNESS_ROOT overrides the root for tests.
"""
import filecmp
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(os.environ.get("DEVARNESS_ROOT") or Path(__file__).resolve().parents[1])
CLONE = ROOT / "Harness" / "prompt-master"
TARGET = ROOT / ".claude" / "skills" / "prompt-master"


def source():
    for candidate in (CLONE / "skills" / "prompt-master", CLONE):
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def wanted(base):
    files = [Path("SKILL.md")]
    if (base / "references").is_dir():
        files += sorted(p.relative_to(base) for p in (base / "references").rglob("*") if p.is_file())
    return files


def check():
    base = source()
    if base is None:
        print("clone missing: no SKILL.md under %s" % CLONE)
        return 1
    files = wanted(base)
    different = [str(p) for p in files
                 if not (TARGET / p).is_file() or not filecmp.cmp(base / p, TARGET / p, shallow=False)]
    for path in different:
        print("differs: " + path)
    print("prompt-master: %d files, %d differ" % (len(files), len(different)))
    return 1 if different else 0


def install():
    base = source()
    if base is None:
        print("clone missing: no SKILL.md under %s" % CLONE)
        return 1
    TARGET.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base / "SKILL.md", TARGET / "SKILL.md")
    if (base / "references").is_dir():
        shutil.rmtree(TARGET / "references", ignore_errors=True)
        shutil.copytree(base / "references", TARGET / "references")
    return check()


if __name__ == "__main__":
    if sys.argv[1:] == ["--install"]:
        sys.exit(install())
    if sys.argv[1:] == ["--check"]:
        sys.exit(check())
    print(__doc__)
    sys.exit(2)
