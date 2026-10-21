#!/usr/bin/env python3
"""TieItUp readiness: its files, the router's pointer, what moved since it was checked, open proposals.

problems(root) lists what is missing, which makes the start check DEGRADED and
sends agents back to Ponytail. stale(root) lists why TieItUp needs a new look,
a change to Ponytail's skills or a harness past the benchmark, which the start
check shows without DEGRADED. proposals(root) counts what `tieitup learn`
would list. All three are read-only and offline; the command answers the
questions. `--notify`, the after-step of Ponytail's row in Library/updates.txt,
sends one needs-owner alert per new Ponytail skills tree and always exits 0.
"""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SKILL = '.claude/skills/tieitup/SKILL.md'
REQUIRED = (
    SKILL,
    '.claude/skills/tieitup/references/rules.md',
    '.claude/skills/tieitup/references/review.md',
    '.claude/skills/tieitup/references/python.md',
    '.claude/skills/tieitup/references/c.md',
    '.agents/skills/tieitup/SKILL.md',
    'Library/bin/tieitup',
    'Library/ponytail/skills/ponytail/SKILL.md',
    'Library/ponytail/skills/ponytail-review/SKILL.md',
)
NOTIFIED = 'Library/.runtime/tieitup/notified.json'
NOTIFY_TIMEOUT = 30


def problems(root):
    issues = ['missing ' + rel for rel in REQUIRED if not (root / rel).is_file()]
    router = root / 'CLAUDE.md'
    if not issues and (not router.is_file() or SKILL not in router.read_text(encoding='utf-8')):
        issues.append('router does not name ' + SKILL)
    return issues


def command(root):
    loader = SourceFileLoader('tieitup_command', str(root / 'Library/bin/tieitup'))
    module = module_from_spec(spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


def missing_counterparts(skill_text, names):
    rows = {line.split('|')[1].strip() for line in skill_text.splitlines() if line.startswith('| ')}
    return [name for name in names if name not in rows]


def stale(root):
    try:
        module = command(root)
    except Exception as error:   # an unreadable command must not break the start check; say so instead
        return ['TieItUp command unreadable: %s' % type(error).__name__]
    skills = root / 'Library/ponytail/skills'
    names = sorted(path.name for path in skills.iterdir() if path.is_dir()) if skills.is_dir() else []
    skill_text = (root / SKILL).read_text(encoding='utf-8')
    return (module.ponytail_changes(root)
            + ['Ponytail skill %s has no TieItUp counterpart' % name
               for name in missing_counterparts(skill_text, names)]
            + module.harness_changes(root))


def proposals(root):
    try:
        return len(command(root).proposals(root / 'Library/.runtime/tieitup', root))
    except Exception:  # an unreadable record or command must not break the start check
        return 0


def send_alert(root, message):
    """notify needs-owner; its exit status, or 1 when it could not run."""
    try:
        return subprocess.run(
            [sys.executable, str(root / 'Library/bin/notify'), 'needs-owner', 'Peter', 'TieItUp', message],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=NOTIFY_TIMEOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def notify_owner(root, send=send_alert):
    """One alert per Ponytail skills tree that needs a re-check; an alert that fails is tried at the next move."""
    try:
        module = command(root)
        changes, tree = module.ponytail_changes(root), module.ponytail_rev(root, 'HEAD:skills')
    except Exception:  # update-tools holds a tool whose after-step fails; an alert is never worth that
        return 0
    if not changes or not tree:
        return 0
    seen = root / NOTIFIED
    try:
        with open(str(seen), encoding='utf-8') as fh:
            if json.load(fh).get('tree') == tree:
                return 0
    except (OSError, ValueError, AttributeError):
        pass                     # no record of an earlier alert: send one
    if send(root, "Ponytail's skills changed at %s; the next session re-checks the conflicts table before coding"
            % tree[:7]) != 0:
        return 0
    seen.parent.mkdir(parents=True, exist_ok=True)
    temp = seen.with_name(seen.name + '.tmp')
    with open(str(temp), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(json.dumps({'version': 1, 'tree': tree}) + '\n')
    os.replace(str(temp), str(seen))
    return 0


if __name__ == '__main__':
    if sys.argv[1:] == ['--notify']:
        raise SystemExit(notify_owner(ROOT))
    issues = problems(ROOT)
    if issues:
        print('TieItUp: %s; agents fall back to Ponytail (.claude/skills/ponytail/SKILL.md)' % '; '.join(issues))
        raise SystemExit(1)
    reasons = stale(ROOT)
    print('TieItUp stale: ' + '; '.join(reasons) if reasons else 'TieItUp ready')
