#!/usr/bin/env python3
"""check_refs — print each `path:line` citation in a document beside the lines it names.

usage: python3 .claude/skills/delegate/check_refs.py DOC.md [DOC.md ...]

A citation is a backticked `path:line`, `path:a-b` or `path:a,b-c` whose path
is relative to the dev root. Each is printed with the
paragraph that makes the claim and the lines the file holds now, so a moved
reference shows. Exits 1 when a cited file is missing or a line is past its
end: that part needs no reader.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CITE = re.compile(r"`([^`\n]+?):(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)`")


def spans(numbers):
    for part in numbers.split(","):
        first, _, last = part.partition("-")
        yield int(first), int(last or first)


def check(doc: Path) -> int:
    text = doc.read_text(encoding="utf-8")
    dead = 0
    for m in CITE.finditer(text):
        path = m.group(1)
        # A bare name is a short form such as `sys_app.c:566` unless it is a
        # root file such as CLAUDE.md; a URL's port is not a line.
        if "://" in path or ("/" not in path and not (ROOT / path).is_file()):
            continue
        claim = " ".join(text[max(0, m.start() - 160):m.end() + 100].split())
        print("=" * 78)
        print("%s:%d  ->  %s:%s" % (doc.name, text.count("\n", 0, m.start()) + 1, path, m.group(2)))
        print("CLAIM:", claim)
        target = ROOT / path
        if not target.is_file():
            print("   missing: no such file under the dev root")
            dead += 1
            continue
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        for first, last in spans(m.group(2)):
            if last > len(lines):
                print("   missing: line %d is past the end (%d lines)" % (last, len(lines)))
                dead += 1
                continue
            for n in range(first, min(last, first + 5) + 1):
                print("   %5d| %s" % (n, lines[n - 1][:140]))
    return dead


def main(argv) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    dead = sum(check(Path(doc)) for doc in argv)
    print("%d dead citation(s)" % dead)
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
