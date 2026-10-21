"""Reversible library-only profile for owned dev:skill links.

Only symlinks at root/.claude/skills/NAME and root/.agents/skills/NAME are
considered, only for policy entries 'dev:skill:NAME' with mode 'library-only'.
Entries without a mode (for example aliases-only entries) request no discovery
change and are skipped; explicit modes must be one of MODES. Every mutation is
preceded by an all-or-nothing preflight; apply writes a recovery backup before
unlinking anything and rechecks each link immediately before unlinking it.
Nothing here deletes directories, follows crafted paths, runs subprocesses or
touches vendor sources. There is deliberately no apply CLI: callers use the
API after checking their own index and query receipts.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

SCHEMA = 1
CLIENTS = ('.claude', '.agents')
MODES = ('library-only', 'task-triggered', 'always-on')
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{0,63}$')
BACKUP_REL = ('.claude', 'hooks', 'library', 'profile-backup.json')
PRESENT_KEYS = {'name', 'path', 'present', 'target', 'resolved'}
ABSENT_KEYS = {'name', 'path', 'present'}


def _real(path):
    return Path(os.path.realpath(path))


def _same(a, b):
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def _norm_target(text):
    return text[4:] if text.startswith('\\\\?\\') else text


def _inside(path, base):
    try:
        rel = path.relative_to(base)
    except ValueError:
        return False
    return rel.parts != ()


def _library_names(policy):
    if not isinstance(policy, dict) or not isinstance(policy.get('entries', {}), dict):
        raise ValueError('policy must be {"entries": {...}}')
    names = []
    for key, entry in policy.get('entries', {}).items():
        if not isinstance(key, str) or not key.startswith('dev:skill:'):
            continue
        name = key[len('dev:skill:'):]
        if not NAME_RE.match(name):
            raise ValueError(f'invalid skill name in policy: {key!r}')
        if not isinstance(entry, dict):
            raise ValueError(f'invalid policy entry for {key!r}')
        if 'mode' not in entry:
            continue
        if entry['mode'] not in MODES:
            raise ValueError(f'invalid mode for {key!r}: {entry["mode"]!r}')
        if entry['mode'] == 'library-only':
            names.append(name)
    return sorted(set(names))


def _expected_paths(names):
    return {f'{client}/skills/{name}' for name in names for client in CLIENTS}


def _candidate(realroot, client, name):
    """Return (link path, relative string) after checking the parent is not redirected."""
    skills = realroot / client / 'skills'
    if not _same(_real(skills), skills):
        raise ValueError(f'{client}/skills is redirected outside its real location')
    return skills / name, f'{client}/skills/{name}'


def _owned_dir(realroot, parts, create):
    """Walk realroot/parts one component at a time, refusing links, junctions and files.

    Each existing component must resolve to itself, so a redirected component can
    never cause a write elsewhere. With create, missing components are made one at
    a time (never parents=True) and rechecked after creation.
    """
    path = realroot
    for part in parts:
        path = path / part
        if not os.path.lexists(path):
            if not create:
                return path
            path.mkdir()
        if path.is_symlink() or not path.is_dir() or not _same(_real(path), path):
            raise ValueError(f'redirected or non-directory path component: {path}')
    return path


def _check_source(realroot, resolved):
    allowed = (_real(realroot / 'Library'), _real(realroot / '.claude' / 'skills'))
    if not any(_inside(resolved, base) for base in allowed):
        raise ValueError(f'link target outside owned boundaries: {resolved}')
    if not resolved.is_dir() or not (resolved / 'SKILL.md').is_file():
        raise ValueError(f'link target is not a skill directory: {resolved}')


def _read_link(realroot, link):
    target = os.readlink(link)
    resolved = _real(link)
    if not resolved.exists():
        raise ValueError(f'broken link: {link}')
    _check_source(realroot, resolved)
    return target, resolved


def snapshot(root, policy):
    realroot = _real(root)
    entries = []
    for name in _library_names(policy):
        for client in CLIENTS:
            link, rel = _candidate(realroot, client, name)
            if link.is_symlink():
                target, resolved = _read_link(realroot, link)
                entries.append({'name': name, 'path': rel, 'present': True,
                                'target': target, 'resolved': str(resolved)})
            elif os.path.lexists(link):
                raise ValueError(f'refusing non-symlink candidate: {rel}')
            else:
                entries.append({'name': name, 'path': rel, 'present': False})
    return {'schema': SCHEMA, 'root': str(realroot), 'entries': entries}


def _validated(root, snap):
    """Validate snapshot shape and identity; return [(entry, link path)]."""
    realroot = _real(root)
    if not isinstance(snap, dict) or snap.get('schema') != SCHEMA \
            or set(snap) != {'schema', 'root', 'entries'}:
        raise ValueError('unsupported snapshot schema')
    if snap['root'] != str(realroot):
        raise ValueError('snapshot root identity does not match root')
    if not isinstance(snap['entries'], list):
        raise ValueError('snapshot entries must be a list')
    out, seen = [], set()
    for entry in snap['entries']:
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) \
                or not NAME_RE.match(entry['name']):
            raise ValueError('invalid snapshot entry name')
        present = entry.get('present')
        if present is not True and present is not False:
            raise ValueError('invalid snapshot presence flag')
        if set(entry) != (PRESENT_KEYS if present else ABSENT_KEYS):
            raise ValueError('unexpected snapshot entry keys')
        client = entry['path'].split('/', 1)[0] if isinstance(entry['path'], str) else None
        if client not in CLIENTS:
            raise ValueError('invalid snapshot path')
        link, rel = _candidate(realroot, client, entry['name'])
        if entry['path'] != rel or rel in seen:
            raise ValueError(f'invalid or duplicate snapshot path: {entry["path"]!r}')
        seen.add(rel)
        if present:
            if not isinstance(entry['target'], str) or not isinstance(entry['resolved'], str):
                raise ValueError('invalid snapshot target')
            resolved = Path(entry['resolved'])
            if _real(os.path.join(link.parent, _norm_target(entry['target']))) != resolved:
                raise ValueError(f'snapshot target does not match resolved path: {rel}')
            _check_source(realroot, resolved)
        out.append((entry, link))
    return realroot, out


def _matches(link, entry):
    return (link.is_symlink()
            and _norm_target(os.readlink(link)) == _norm_target(entry['target'])
            and str(_real(link)) == entry['resolved'])


def _write_backup(realroot, snap):
    """Write the recovery backup; never overwrite or disturb a differing prior one."""
    parent = _owned_dir(realroot, BACKUP_REL[:-1], create=True)
    if not _inside(_real(parent), realroot / '.claude'):
        raise ValueError('backup directory escapes root/.claude')
    path = parent / BACKUP_REL[-1]
    data = json.dumps(snap, indent=2, sort_keys=True) + '\n'
    if os.path.lexists(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError('backup path is not a regular file')
        if path.read_text(encoding='utf-8') != data:
            raise RuntimeError(f'differing backup exists; refusing to overwrite {path}')
        return path
    tmp = path.with_name(path.name + '.tmp')
    handle = open(tmp, 'x', encoding='utf-8')
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.lexists(tmp) and not tmp.is_symlink():
            tmp.unlink()
        raise
    return path


def apply_profile(root, policy, snap):
    """Remove library-only links recorded in snap.

    The caller must have checked its current index and query receipts first.
    """
    realroot, items = _validated(root, snap)
    if {e['path'] for e, _ in items} != _expected_paths(_library_names(policy)):
        raise ValueError('snapshot does not cover both client paths for every library-only name')
    to_remove = []
    for entry, link in items:
        if link.is_symlink():
            if not entry['present'] or not _matches(link, entry):
                raise RuntimeError(f'link changed since snapshot: {entry["path"]}')
            to_remove.append((entry, link))
        elif os.path.lexists(link):
            raise RuntimeError(f'non-symlink now present: {entry["path"]}')
    if not to_remove:
        return {'removed': []}
    _write_backup(realroot, snap)
    removed = []
    for entry, link in to_remove:
        # Best-effort race mitigation only: no lock binds foreign processes.
        client = entry['path'].split('/', 1)[0]
        if _candidate(realroot, client, entry['name'])[0] != link or not _matches(link, entry):
            raise RuntimeError(f'link changed before unlink: {entry["path"]}; '
                               f'already removed: {removed}; backup kept')
        link.unlink()
        removed.append(entry['path'])
    return {'removed': removed}


def restore_profile(root, snap):
    realroot, items = _validated(root, snap)
    to_create = []
    for entry, link in items:
        if link.is_symlink():
            if not entry['present'] or not _matches(link, entry):
                raise RuntimeError(f'foreign link present: {entry["path"]}')
        elif os.path.lexists(link):
            raise RuntimeError(f'foreign directory or file present: {entry["path"]}')
        elif entry['present']:
            client = entry['path'].split('/', 1)[0]
            _owned_dir(realroot, (client, 'skills'), create=False)
            to_create.append((entry, link, client))
    restored = []
    for entry, link, client in to_create:
        parent = _owned_dir(realroot, (client, 'skills'), create=True)
        if parent != link.parent:
            raise RuntimeError(f'restore parent changed: {entry["path"]}')
        os.symlink(entry['target'], link, target_is_directory=True)
        restored.append(entry['path'])
        if not _matches(link, entry):
            raise RuntimeError(f'restored link does not match snapshot: {entry["path"]}')
    return {'restored': restored}


def _load_json(path):
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--snapshot', required=True, type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    snap_cmd = sub.add_parser('snapshot', help='record current links (no link changes)')
    snap_cmd.add_argument('--policy', required=True, type=Path)
    sub.add_parser('restore', help='recreate links recorded in --snapshot')
    args = parser.parse_args(argv)
    if args.command == 'snapshot':
        snap = snapshot(args.root, _load_json(args.policy))
        with open(args.snapshot, 'x', encoding='utf-8') as handle:
            json.dump(snap, handle, indent=2, sort_keys=True)
            handle.write('\n')
        result = {'entries': len(snap['entries'])}
    else:
        result = restore_profile(args.root, _load_json(args.snapshot))
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
