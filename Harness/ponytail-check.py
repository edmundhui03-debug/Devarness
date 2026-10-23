#!/usr/bin/env python3
"""Read-only inventory of pinned Ponytail and dev's instruction-based activation."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def problems(root):
    try:
        pin = next(row.split('\t')[2] for row in
                   (root / 'Harness/repos.txt').read_text().splitlines()
                   if row.startswith('Harness/ponytail\t'))
    except (OSError, StopIteration, IndexError):
        return ['Ponytail manifest pin missing']
    issues = []
    for name in ('Harness/ponytail/skills/ponytail/SKILL.md',
                 'Harness/ponytail/skills/ponytail-review/SKILL.md',
                 '.claude/skills/ponytail/SKILL.md', '.agents/skills/ponytail/SKILL.md'):
        if not (root / name).is_file():
            issues.append('missing ' + name)
    try:
        actual = subprocess.check_output(
            ['git', '-C', str(root / 'Harness/ponytail'), 'rev-parse', 'HEAD'],
            text=True, stderr=subprocess.DEVNULL, timeout=5).strip()
        if actual != pin:
            issues.append('Ponytail pin mismatch; restore Harness/repos.txt revision')
    except (OSError, subprocess.SubprocessError):
        issues.append('Ponytail revision unavailable')
    router = root / 'CLAUDE.md'
    if not router.is_file() or '.claude/skills/ponytail/SKILL.md' not in router.read_text():
        issues.append('Ponytail router activation missing')
    return issues


if __name__ == '__main__':
    issues = problems(ROOT)
    print('\n'.join(issues) if issues else
          'Ponytail ready: pinned skills and both agent adapters; dev default full (instruction-based)')
    raise SystemExit(bool(issues))
