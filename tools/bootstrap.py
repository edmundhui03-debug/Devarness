#!/usr/bin/env python3
"""Read-only by default; fetch approved public sources only on explicit request."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

def parse_manifest(text):
    entries = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) not in (3, 4):
            raise ValueError('Manifest requires path, public URL and commit')
        relative, url, pin = fields[:3]
        path = PurePosixPath(relative)
        parsed = urlsplit(url)
        if (path.is_absolute() or '..' in path.parts or '.' in path.parts
                or '\\' in relative or len(path.parts) < 2
                or path.parts[0] != 'Library' or '.git' in path.parts):
            raise ValueError('Manifest path must remain inside Library')
        if (parsed.scheme != 'https' or parsed.hostname != 'github.com'
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or not re.fullmatch(r'/[\w.-]+/[\w.-]+(?:\.git)?', parsed.path)):
            raise ValueError('Manifest requires an unauthenticated public GitHub URL')
        if not re.fullmatch(r'[0-9a-f]{40}', pin):
            raise ValueError('Manifest requires a full commit pin')
        entries.append({'path': relative, 'url': url, 'pin': pin,
                        'sparse': fields[3].split() if len(fields) == 4 else []})
    return entries

def skill_target(root, relative, link):
    root = root.resolve()
    path = root / relative
    destination = (path.parent / link).resolve()
    try:
        path.parent.resolve().relative_to(root)
        destination.relative_to(root)
    except ValueError:
        raise ValueError('Skill link escapes checkout: ' + relative)
    return destination

def readiness(root=ROOT):
    required = ['CLAUDE.md', 'AGENTS.md', 'LICENSE', 'Library/repos.txt',
                'tools/release_check.py', '.claude/hooks/guard_git_amend.py']
    missing = [path for path in required if not (root / path).is_file()]
    if sys.version_info < (3, 9):
        missing.append('Python 3.9+')
    if not shutil.which('git'):
        missing.append('Git')
    entries = parse_manifest((root / 'Library/repos.txt').read_text(encoding='utf-8'))
    return {'schema': 1, 'core_ready': not missing, 'missing': missing,
            'optional_sources_present': sum((root / e['path'] / '.git').exists() for e in entries),
            'optional_sources_total': len(entries)}

def run(*args):
    subprocess.run(list(args), check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

def fetch(entry):
    destination = ROOT / entry['path']
    # Resolve the parent before Git can create files through an existing junction.
    skill_target(ROOT, entry['path'], destination.name)
    if destination.exists():
        if not (destination / '.git').exists():
            raise ValueError('Refusing existing non-repository: ' + entry['path'])
        head = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
        if head != entry['pin']:
            raise ValueError('Existing source is off-pin; review it first: ' + entry['path'])
        print('Pinned source already present:', entry['path'])
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    run('git', '-c', 'core.autocrlf=false', '-c', 'core.symlinks=true',
        '-c', 'core.longpaths=true', 'clone', '--filter=blob:none', '--no-checkout',
        entry['url'], str(destination))
    if entry['path'] == 'Library/reverse-skill':
        run('git', '-C', str(destination), 'sparse-checkout', 'init', '--no-cone')
        exclude = destination / '.git/info/sparse-checkout'
        with exclude.open('w', encoding='utf-8', newline='\n') as stream:
            stream.write('/*\n!/skills/pentest-tools/src-hunter/references/payloader/\n')
    elif entry['sparse']:
        run('git', '-C', str(destination), 'sparse-checkout', 'init', '--cone')
        run('git', '-C', str(destination), 'sparse-checkout', 'set', *entry['sparse'])
    run('git', '-C', str(destination), 'checkout', '--detach', entry['pin'])
    print('Fetched source only:', entry['path'])

def link_skills():
    links = json.loads((ROOT / 'tools/skill-links.json').read_text(encoding='utf-8'))['links']
    missing = []
    for relative, link in links.items():
        source = skill_target(ROOT, relative, link)
        if not (source / 'SKILL.md').is_file():
            missing.append(relative)
            continue
        path = ROOT / relative
        if path.is_symlink():
            if path.resolve() != source:
                raise ValueError('Existing skill points elsewhere: ' + relative)
            if path.is_dir():
                continue
            # Windows reparse targets need native separators even though the
            # tracked link metadata is portable POSIX text.
            path.unlink()
        if path.exists():
            if not path.is_file() or path.read_text(encoding='utf-8').strip() != link:
                raise ValueError('Refusing to overwrite a different skill: ' + relative)
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.symlink_to(os.path.normpath(link), target_is_directory=True)
        except OSError:
            if not path.exists():
                with path.open('w', encoding='utf-8', newline='\n') as stream:
                    stream.write(link)
            raise ValueError('Native directory links unavailable; enable Windows Developer Mode and retry')
    print('Local skill links checked; optional sources missing:', len(missing))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--fetch', nargs='+', metavar='TOOL')
    parser.add_argument('--link-skills', action='store_true')
    parser.add_argument('--no-system', action='store_true', help='compatibility: onboarding is always checkout-local')
    args = parser.parse_args()
    entries = parse_manifest((ROOT / 'Library/repos.txt').read_text(encoding='utf-8'))
    if args.list:
        for entry in entries:
            print(Path(entry['path']).name, entry['pin'], entry['url'])
    if args.fetch:
        by_name = {Path(e['path']).name: e for e in entries}
        unknown = sorted(set(args.fetch) - set(by_name))
        if unknown:
            raise ValueError('Unknown source IDs: ' + ', '.join(unknown))
        for name in args.fetch:
            fetch(by_name[name])
    if args.link_skills:
        link_skills()
    state = readiness()
    print(json.dumps(state) if args.json else
          ('Devarness core ready' if state['core_ready'] else 'Devarness core missing: ' + ', '.join(state['missing'])))
    return 0 if state['core_ready'] else 1

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Devarness setup failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
