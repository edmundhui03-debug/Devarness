#!/usr/bin/env python3
"""Install/check the pinned shared browser and OCR runtime. No hook changes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

LIBRARY = Path(__file__).resolve().parent
ROOT = LIBRARY.parent


def run(*args):
    # Windows cannot start a .cmd wrapper such as npm by its bare name;
    # which() resolves the full path there and finds the same program elsewhere.
    command = [str(a) for a in args]
    subprocess.run([shutil.which(command[0]) or command[0], *command[1:]], check=True)


def link(source, target):
    if target.is_symlink() and target.resolve() == source.resolve():
        return
    if target.exists() or target.is_symlink():
        raise RuntimeError('Refusing to overwrite ' + str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(os.path.relpath(source, target.parent), target_is_directory=source.is_dir())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--install', action='store_true')
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    doc = LIBRARY / '.runtime/docling'
    browser = LIBRARY / '.runtime/playwright-cli'
    python = doc / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if args.install:
        for name in ('docling', 'playwright-cli'):
            pin = next(s.split('\t')[2] for s in (LIBRARY / 'repos.txt').read_text().splitlines()
                       if s.startswith('Harness/' + name + '\t'))
            actual = subprocess.check_output(['git', '-C', str(LIBRARY / name), 'rev-parse', 'HEAD'], text=True).strip()
            if actual != pin:
                raise RuntimeError('Restore the manifest pin for ' + name)
        if not python.exists():
            run('uv', 'venv', '--python', '3.12', doc / '.venv')
        run('uv', 'pip', 'install', '--python', python, '-r', LIBRARY / 'browser-docs-requirements.txt')
        browser.mkdir(parents=True, exist_ok=True)
        for name in ('package.json', 'package-lock.json'):
            shutil.copy2(LIBRARY / 'browser-docs-node' / name, browser / name)
        run('npm', 'ci', '--prefix', browser)
        for base in ('.claude/skills', '.agents/skills'):
            link(LIBRARY / 'shared-skills/browser-docs', ROOT / base / 'browser-docs')
        for name in ('browser', 'ocr'):
            link(LIBRARY / 'bin' / name, Path.home() / '.local/bin' / name)
    checks = {
        'docling_package': python.is_file() and (
            any((doc / '.venv').glob('lib/python*/site-packages/docling/__init__.py')) or
            (doc / '.venv/Lib/site-packages/docling/__init__.py').is_file()),
        'browser_cli': (browser / 'node_modules/@playwright/cli/playwright-cli.js').is_file(),
        'shared_skills': all((ROOT / base / 'browser-docs/SKILL.md').is_file()
                            for base in ('.claude/skills', '.agents/skills')),
    }
    print(json.dumps({'inventory': checks, 'runtime_tests': 'see verification record'}, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
