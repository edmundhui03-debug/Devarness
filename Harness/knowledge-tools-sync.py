#!/usr/bin/env python3
"""Install pinned shared knowledge/diagram tools without changing upstream clones.

--check inventories files only; --install prepares dependencies and links.
Run the install on each device after bootstrap has restored repos.txt clones.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

LIBRARY = Path(__file__).resolve().parent
ROOT = LIBRARY.parent
UA_NAMES = ('understand', 'understand-chat', 'understand-dashboard', 'understand-diff',
            'understand-domain', 'understand-explain', 'understand-figma',
            'understand-knowledge', 'understand-onboard')


def discovery_names(project):
    """Root-only library policy never changes a satellite's skill profile."""
    names = (*UA_NAMES, 'diagram-design')
    policy = ROOT / 'Harness/library-policy.json'
    if project.resolve() != ROOT.resolve():
        return names
    if not policy.is_file():
        raise ValueError('root library policy is missing; refusing discovery changes')
    data = json.loads(policy.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('library policy must be an object')
    entries = data.get('entries')
    if not isinstance(entries, dict):
        raise ValueError('library policy entries must be an object')
    for name in names:
        entry = entries.get('dev:skill:' + name, {})
        if not isinstance(entry, dict):
            raise ValueError('library policy entry must be an object: ' + name)
        mode = entry.get('mode', 'task-triggered')
        if mode not in ('library-only', 'task-triggered', 'always-on'):
            raise ValueError('invalid library activation mode: ' + name)
    return tuple(name for name in names
                 if entries.get('dev:skill:' + name, {}).get('mode') != 'library-only')


def pins():
    return {line.split('\t')[0]: line.split('\t')[2] for line in
            (LIBRARY / 'repos.txt').read_text().splitlines() if line and not line.startswith('#')}


def tree(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file()}


def own_link(target):
    """A link that resolves under Library is one this installer made at an earlier pin.

    Harness/.runtime may itself be a link, as in a worktree run through
    linked_run.py, so where it really is counts as under Library too.
    """
    try:
        if not target.is_symlink():
            return False
        resolved = target.resolve()
        runtime = (LIBRARY / '.runtime').resolve()
        return LIBRARY in resolved.parents or resolved == runtime or runtime in resolved.parents
    except OSError:
        return False


def link(source, target, pristine_copy=None):
    target.parent.mkdir(parents=True, exist_ok=True)
    text = os.path.relpath(source, target.parent)
    # The link's text, not where it resolves: a tracked link naming a revision
    # resolves where one naming `current` does, and must still be rewritten.
    if target.is_symlink() and os.path.normpath(os.readlink(target)) == os.path.normpath(text):
        return
    if target.exists() or target.is_symlink():
        # Copies produced by skill-installer can be replaced only if byte-identical.
        if pristine_copy and target.is_dir() and not target.is_symlink() and tree(target) == tree(pristine_copy):
            shutil.rmtree(target)
        elif own_link(target):
            # update-tools moved the pin: the link points at the runtime of the
            # old commit, which this installer made; replacing it is the job.
            target.unlink()
        else:
            raise RuntimeError('Refusing to replace existing path: ' + str(target))
    target.symlink_to(text, target_is_directory=source.is_dir())


def run(*args, cwd=None):
    # Windows cannot start a .cmd wrapper such as corepack by its bare name;
    # which() resolves the full path there and finds the same program elsewhere.
    subprocess.run([shutil.which(args[0]) or args[0], *args[1:]], cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--install', action='store_true')
    parser.add_argument('--project', action='append', default=[], type=Path,
                        help='Additional dev project root needing skill discovery')
    args = parser.parse_args()
    manifest = pins()
    ua_clone = LIBRARY / 'Understand-Anything'
    diagram = LIBRARY / 'diagram-design'
    revision = manifest['Harness/Understand-Anything']
    runtime = LIBRARY / '.runtime/understand-anything' / revision
    plugin = runtime / 'understand-anything-plugin'
    # Tracked links name this per-device alias, never a revision: a pin moved
    # on one device then changes no tracked file, and another device's links
    # keep working on its old runtime until its own install moves the alias.
    current = runtime.parent / 'current'
    shared_plugin = current / 'understand-anything-plugin'
    pyenv = LIBRARY / '.runtime/diagram-tools'
    python = pyenv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    projects = [ROOT]
    for project in args.project:
        project = project.resolve()
        project.relative_to(ROOT)
        if not project.is_dir():
            parser.error('Project does not exist: ' + str(project))
        if project not in projects:
            projects.append(project)
    if args.install:
        for clone in (ua_clone, diagram):
            # repos.txt keys use forward slashes; str() of a Windows path does not.
            expected = manifest[clone.relative_to(ROOT).as_posix()]
            actual = subprocess.check_output(['git', '-C', str(clone), 'rev-parse', 'HEAD'], text=True).strip()
            if expected != actual:
                raise RuntimeError('Clone differs from manifest pin: ' + str(clone))
        if not runtime.exists():
            runtime.mkdir(parents=True)
            with tempfile.TemporaryFile() as stream:
                subprocess.run(['git', '-C', str(ua_clone), 'archive', revision], stdout=stream, check=True)
                stream.seek(0)
                with tarfile.open(fileobj=stream) as archive:
                    archive.extractall(runtime)
        # pnpm itself when it is on PATH (NEW_DEVICE installs it with npm); Corepack only without it.
        pnpm = ['pnpm'] if shutil.which('pnpm') else ['corepack', 'pnpm']
        if pnpm[0] == 'corepack':
            corepack = shutil.which('corepack')
            if not corepack:
                raise RuntimeError('Install Node 22+ with Corepack, then retry')
            pnpm_js = Path(corepack).resolve().with_name('pnpm.js')
            if not pnpm_js.is_file() or os.name == 'nt':
                raise RuntimeError('Enable pnpm on PATH with Corepack, then retry')
            link(pnpm_js, Path.home() / '.local/bin/pnpm')
        if not (plugin / 'packages/viewer/dist/index.html').exists():
            run(*pnpm, 'install', '--frozen-lockfile', cwd=runtime)
            run(*pnpm, '--filter', '@understand-anything/skill', 'build', cwd=runtime)
            run(*pnpm, '--filter', 'understand-anything-viewer', 'build', cwd=runtime)
        link(runtime, current)          # only once this revision has built
        for old in runtime.parent.iterdir():  # superseded revisions serve nothing
            if old not in (runtime, current) and old.is_dir() and not old.is_symlink():
                shutil.rmtree(old, ignore_errors=True)
        if not python.exists():
            run('uv', 'venv', '--python', '3.12', str(pyenv))
        probe = subprocess.run([str(python), '-c', "import importlib.metadata; assert importlib.metadata.version('playwright') == '1.58.0'"], capture_output=True)
        if probe.returncode:
            run('uv', 'pip', 'install', '--python', str(python), 'playwright==1.58.0')
        run(str(python), '-m', 'playwright', 'install', 'chromium')
        for project in projects:
            for name in discovery_names(project):
                source = (diagram / 'skills/diagram-design' if name == 'diagram-design'
                          else shared_plugin / 'skills' / name)
                old = (diagram / 'skills/diagram-design' if name == 'diagram-design'
                       else ua_clone / 'understand-anything-plugin/skills' / name)
                for client in ('.claude', '.agents'):
                    link(source, project / client / 'skills' / name, pristine_copy=old)
            marker = project / '.diagram-design'
            if not marker.exists():
                marker.write_text('profile: house\n')
        link(shared_plugin, Path.home() / '.understand-anything-plugin')
        link(LIBRARY / 'profiles/house.md', Path.home() / '.diagram-design/profiles/house.md')
        for agent in (plugin / 'agents').glob('*.md'):
            link(shared_plugin / 'agents' / agent.name, ROOT / '.claude/agents' / ('ua-' + agent.name))
        for command in ('understand', 'diagram'):
            source = LIBRARY / 'bin' / command
            source.chmod(0o755)
            link(source, Path.home() / '.local/bin' / command)
    rows = []
    for project in projects:
        names = discovery_names(project)
        rows.append({'project': str(project.relative_to(ROOT)) or '.',
                     'expected_skills': len(names),
                     'claude_skills': sum((project / '.claude/skills' / n / 'SKILL.md').is_file() for n in names),
                     'codex_skills': sum((project / '.agents/skills' / n / 'SKILL.md').is_file() for n in names)})
    ready = {'understand_core': (plugin / 'packages/core/dist/index.js').is_file(),
             'understand_viewer': (plugin / 'packages/viewer/dist/index.html').is_file(),
             'diagram_python': python.is_file(),
             'profile': (Path.home() / '.diagram-design/profiles/house.md').is_file(),
             'universal_plugin_root': (Path.home() / '.understand-anything-plugin').resolve() == plugin.resolve(),
             'wrappers': all((Path.home() / '.local/bin' / n).is_file() for n in ('understand', 'diagram'))}
    passed = all(ready.values()) and all(r['claude_skills'] == r['codex_skills'] == r['expected_skills'] for r in rows)
    print(json.dumps({'file_readiness': ready, 'projects': rows, 'passed': passed,
                      'note': 'File inventory; see KNOWLEDGE_TOOLS.md for runtime and discovery verification.'}, indent=2))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
