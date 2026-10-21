#!/usr/bin/env python3
"""names-audit: dev's tracked files name dev, never the old workspace.

Usage: python Library/names-audit.py [ROOT]

Reads every file git tracks under ROOT (default: the repository holding this
script) and prints path:line for each old name (line 0 is the file's own
name): "kb" as a word or a prefix (kb-check, KB_ROOT, kb:skill:x, the word
KB), "rbr" in any case, and "Read Before Run". A number before "KB" makes it
a size unit ("64 KB"), not a name.
History may name the old workspace, so the history files are exempt, and so
are this audit and its test, which must spell out what they look for. Saved
harness-step patches check added lines; context and removals quote history.
Exits 1 when anything is found. Standard library only.
"""
from pathlib import Path
import re
import subprocess
import sys

EXEMPT = ("CHANGES.md", "LESSONS.md", "Setup/AGENT_LEDGER.md", "Setup/superpowers/",
          "Library/laya-eval/", "Library/names-audit.py", "Library/tests/test_names_audit.py")
# Not inside a longer word, number or hash: KB, kb-, kb_, KB_, kb:, -kb, _kb, RBR, .claude/rbr.
KB = re.compile(r"(?<![A-Za-z0-9])kb(?![A-Za-z0-9])", re.IGNORECASE)
SIZE = re.compile(r"\d[\d.,]*\s*$")
OTHER = re.compile(r"(?<![A-Za-z0-9])rbr(?![A-Za-z0-9])|read before run", re.IGNORECASE)


def hits(line):
    """The old names on one line, size units excepted."""
    found = [m.group(0) for m in OTHER.finditer(line)]
    found += [m.group(0) for m in KB.finditer(line) if not SIZE.search(line[:m.start()])]
    return found


def tracked(root):
    listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True,
                             check=True, timeout=120,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    return [name for name in listing.decode("utf-8").split("\0")
            if name and not name.startswith(EXEMPT)]


def audit(root):
    report = []
    for name in tracked(root):
        found = hits(name)
        if found:
            report.append("%s:0: (the file name)  [%s]" % (name, ", ".join(found)))
        path = root / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue
        saved_patch = name.startswith("Setup/harness-steps/") and name.endswith(".diff")
        patch_hunk = False
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if saved_patch:
                if line.startswith("diff --git "):
                    patch_hunk = False
                elif line.startswith("@@ "):
                    patch_hunk = True
                if not line.startswith("+") or (line.startswith("+++") and not patch_hunk):
                    continue
            found = hits(line)
            if found:
                report.append("%s:%d: %s  [%s]" % (name, number, line.strip()[:160], ", ".join(found)))
    return report


def main(argv):
    root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    report = audit(root)
    sys.stdout.reconfigure(errors="backslashreplace")   # a quoted line may not fit a Windows code page
    for entry in report:
        print(entry)
    files = len({entry.split(":", 1)[0] for entry in report})
    print("names-audit: %d old name(s) in %d file(s)" % (len(report), files) if report
          else "names-audit: clean")
    return 1 if report else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
