#!/usr/bin/env python3
"""Install/check the isolated YAML parser and the library entry points.

No plugin registration, hook edits, source pin changes or Git operations.
"""
import argparse
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def python_path(root):
    return root / 'Library/.runtime/library' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def refuse_foreign(source, target):
    if target.exists() or target.is_symlink():
        if not target.is_symlink() or target.resolve() != source.resolve():
            raise RuntimeError('Refusing to replace foreign path: ' + str(target))


def install(root, bindir):
    source = root / 'Library/bin/library'
    target = bindir / 'library'
    refuse_foreign(source, target)
    refuse_foreign(root / '.claude/skills/library', root / '.agents/skills/library')
    uv = shutil.which('uv')
    if not uv:
        raise RuntimeError('uv is missing; install the approved Library prerequisites first')
    runtime = root / 'Library/.runtime/library'
    python = python_path(root)
    if not python.is_file():
        subprocess.run([uv, 'venv', '--python', '3.12', str(runtime)], check=True)
    subprocess.run([uv, 'pip', 'sync', '--require-hashes', '--python', str(python),
                    str(root / 'Library/library-requirements.txt')], check=True)
    helpers = runpy.run_path(str(root / 'Library/codex-setup.py'))
    helpers['link'](root / '.claude/skills/library', root / '.agents/skills/library')
    bindir.mkdir(parents=True, exist_ok=True)
    refuse_foreign(source, target)  # Recheck after dependency installation.
    if not target.is_symlink():
        target.symlink_to(os.path.relpath(source, target.parent))
    if os.name != 'nt':
        source.chmod(source.stat().st_mode | 0o111)


def check(root):
    issues = []
    for relative in ('Library/library.py', 'Library/bin/library', 'Library/library-sources.json',
                     'Library/library-policy.json', '.claude/skills/library/SKILL.md',
                     '.agents/skills/library/SKILL.md'):
        if not (root / relative).is_file():
            issues.append('missing ' + relative)
    python = python_path(root)
    if not python.is_file():
        issues.append('missing isolated refresh parser')
    else:
        result = subprocess.run([str(python), '-c', 'import yaml; assert yaml.__version__ == "6.0.2"'],
                                capture_output=True, timeout=15)
        if result.returncode:
            issues.append('isolated parser check failed')
    return issues


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--install', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.install:
            install(ROOT, Path.home() / '.local/bin')
        issues = check(ROOT)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print('library setup ERROR: ' + str(exc), file=sys.stderr)
        return 2
    print('\n'.join(issues) if issues else 'Library files/parser ready; session exposure and runtime use not inferred')
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
