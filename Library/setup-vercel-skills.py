#!/usr/bin/env python3
"""Install/check the locked Vercel CLI in Library/.runtime; never install skills."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'Library/.runtime/vercel-skills'
LOCKS = ROOT / 'Library/runtime-locks/vercel-skills'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--install', action='store_true')
    action.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.install:
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            print('vercel-skills: npm missing')
            return 1
        RUNTIME.mkdir(parents=True, exist_ok=True)
        for name in ('package.json', 'package-lock.json'):
            shutil.copyfile(LOCKS / name, RUNTIME / name)
        result = subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
                                cwd=RUNTIME, timeout=180,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            return result.returncode
    cli = RUNTIME / 'node_modules/skills/bin/cli.mjs'
    package = RUNTIME / 'node_modules/skills/package.json'
    if not cli.is_file() or not package.is_file():
        print('vercel-skills: runtime missing')
        return 1
    version = json.loads(package.read_text(encoding='utf-8'))['version']
    if version != '1.7.2' or (RUNTIME / 'package-lock.json').read_bytes() != (LOCKS / 'package-lock.json').read_bytes():
        print('vercel-skills: runtime differs from lock; rerun --install')
        return 1
    print(f'vercel-skills: {version} installed; prompt searches use curated keywords')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
