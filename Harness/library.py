"""Offline library index: build, validate, search, pick and a small CLI.

Queries read only the saved JSON index; coverage also lists what the tree
holds (skill folders, Harness/bin, agent briefs, MCP registrations, clones).
YAML is imported lazily inside build_index; nothing here starts processes or
opens network connections.
Client exposure is never inferred: configured_clients stays [] and
runtime_status stays 'unknown'. Plugin roots ('@plugin:<key>') are resolved
read-only from the installed-plugins registry; nothing is installed or
registered. A fresh snapshot is not proof of runtime safety.
Owners come from the router's ownership table (the '| Domain | Owner |'
table): an owner_ref 'FILE|KEY' names the one row whose domain starts with
KEY's words, so rewording the rest of a row does not break the lookup.
Search and pick scores are lexical relevance, never safety or confidence.
"""
import argparse
import codecs
import copy
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

SCHEMA = 2
READ_LIMIT = 65536
AUX_LIMIT = 1 << 20
INDEX_LIMIT = 64 << 20
MAX_DIRS = 10000
DEFAULT_MODE = 'library-only'
MODES = ('library-only', 'task-triggered', 'always-on')
SOURCE_FIELDS = ('collection', 'kind', 'root', 'pattern', 'scope', 'owner_ref')
SOURCE_OPTIONAL = ('category', 'mode')
POLICY_FIELDS = ('purpose', 'aliases', 'scope', 'mode', 'category', 'exclusions')
ENTRY_FIELDS = {'id': str, 'name': str, 'kind': str, 'collection': str,
                'purpose': str, 'category': str, 'path': str, 'owner_ref': str,
                'owner': (str, type(None)), 'scope': str, 'mode': str,
                'aliases': list, 'exclusions': list, 'source_present': bool,
                'configured_clients': list, 'runtime_status': str,
                'unfinished': bool}
INDEX_KEYS = {'schema', 'fingerprints', 'entries', 'diagnostics', 'router'}
# Optional: what was left out because a plugin is not installed here. Never a fault.
NOTES = 'notes'
ROUTER_FIELDS = ('file', 'domain', 'owner')
IDENT = re.compile(r'^[a-z0-9][a-z0-9_-]*$')
NAME = re.compile(r'^[^\s:/\\]+$')
DRIVE = re.compile(r'^[A-Za-z]:')
IN_PROGRESS = {'in-progress', 'in_progress', 'inprogress', 'wip'}
STOP_WORDS = frozenset('a an the of and or to in for with one this from is on by '
                       'at as be it that into'.split())
WEIGHTS = (('name', 8), ('aliases', 8), ('purpose', 2), ('category', 3))
EXACT_BONUS = 100
MAX_LIMIT = 20
PLUGIN_PREFIX = '@plugin:'
PLUGIN_KEY = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*(?:@[A-Za-z0-9][A-Za-z0-9._-]*)?$')
PLUGIN_RANK = {'local': 0, 'project': 1, 'user': 2}
# Claude Code reads its configuration from CLAUDE_CONFIG_DIR when it is set.
REGISTRY = (Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude')
            / 'plugins' / 'installed_plugins.json')
JUNCTION_TAG = 0xA0000003


# ---------------------------------------------------------------- helpers

def _rel_path(value, what):
    """Normalize a root-relative path; '.' means the workspace root."""
    if not isinstance(value, str):
        raise ValueError(f'{what} must be a string')
    text = value.replace('\\', '/').strip()
    if not text:
        raise ValueError(f'{what} must not be empty')
    if text.startswith(('/', '~')) or DRIVE.match(text):
        raise ValueError(f'{what} must be relative to the workspace root: {value!r}')
    parts = [p for p in text.split('/') if p not in ('', '.')]
    if '..' in parts:
        raise ValueError(f'{what} must not contain "..": {value!r}')
    return '/'.join(parts) or '.'


def _within(project, scope):
    return scope == '.' or project == scope or project.startswith(scope + '/')


def _inside(path, base):
    """Lexical containment of absolute filesystem paths."""
    p = os.path.normcase(os.path.abspath(path))
    b = os.path.normcase(os.path.abspath(base)).rstrip('\\/')
    return p == b or p.startswith(b + os.sep)


def _key(path):
    return os.path.abspath(str(path))


def _is_link(path):
    """True for symlinks and Windows junctions; never follows them."""
    try:
        if os.path.islink(path):
            return True
        isjunction = getattr(os.path, 'isjunction', None)
        if isjunction is not None:
            return isjunction(path)
        return getattr(os.lstat(path), 'st_reparse_tag', 0) == JUNCTION_TAG
    except OSError:
        return False


def _link_target(path):
    if not _is_link(path):
        return ''
    try:
        return os.path.realpath(path)
    except OSError:
        return '?'


def _node(path):
    """Type/link fingerprint for roots, links and anything not readable."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return 'missing'
    except OSError as exc:
        return f'node:error:{type(exc).__name__}'
    if _is_link(path):
        kind = 'link'
    elif stat.S_ISDIR(st.st_mode):
        kind = 'dir'
    elif stat.S_ISREG(st.st_mode):
        kind = 'file'
    else:
        kind = 'other'
    alive = int(os.path.exists(path))
    return f'node:{kind}:{alive}:{st.st_size}:{st.st_mtime_ns}:{_link_target(path)}'


def _file_state(path, limit):
    """Read at most limit+1 bytes; return (bytes or None, fingerprint).

    The fingerprint carries size, mtime_ns and link target, so same-size
    edits past the read cap are still detected without reading the whole file.
    """
    try:
        if not stat.S_ISREG(os.stat(path).st_mode):
            raise IsADirectoryError(str(path))
        with open(path, 'rb') as fh:
            st = os.fstat(fh.fileno())
            data = fh.read(limit + 1)
    except OSError:
        return None, f'unreadable:{limit}:{_node(path)}'
    digest = hashlib.sha256(data).hexdigest()
    return data, (f'file:{limit}:{st.st_size}:{st.st_mtime_ns}:{digest}:'
                  f'{_link_target(path)}')


def _dir_state(path):
    """List one directory; return (sorted entries or None, fingerprint).

    __pycache__ is left out: Python writes it beside any script a test imports,
    and it would make the index look stale without a source changing.
    """
    try:
        with os.scandir(path) as it:
            items = sorted((e for e in it if e.name != '__pycache__'), key=lambda e: e.name)
    except OSError:
        return None, f'unlistable:{_node(path)}'
    names = '\0'.join(e.name for e in items).encode('utf-8', 'surrogatepass')
    return items, f'dir:{hashlib.sha256(names).hexdigest()}:{_link_target(path)}'


def _display(root, path):
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _tokens(text):
    return re.findall(r'[a-z0-9]+', text.lower())


# ---------------------------------------------------------------- parsing

def _strict_loader(yaml):
    class StrictLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        if not isinstance(node, yaml.MappingNode):
            raise yaml.constructor.ConstructorError(
                None, None, 'expected a mapping', node.start_mark)
        seen = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError:
                raise yaml.constructor.ConstructorError(
                    None, None, 'unhashable mapping key', key_node.start_mark)
            if duplicate:
                raise yaml.constructor.ConstructorError(
                    None, None, f'duplicate key {key!r}', key_node.start_mark)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    return StrictLoader


def _front_matter(text, load, truncated=False):
    """Return (meta or None, body); raise ValueError on malformed blocks."""
    lines = text.split('\n')
    if lines[0].rstrip() != '---':
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip() in ('---', '...'):
            meta = load('\n'.join(lines[1:i]))
            if meta is None:
                meta = {}
            if not isinstance(meta, dict):
                raise ValueError('front matter is not a mapping')
            return meta, '\n'.join(lines[i + 1:])
    if truncated:
        raise ValueError(f'front matter not closed within {READ_LIMIT} bytes')
    raise ValueError('unterminated front matter')


def _summary(body):
    """First H1, docstring or leading comment; never arbitrary code."""
    lines = body.split('\n')[:60]
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        i += 1
        if not s or s == '---' or s.startswith('#!'):
            continue
        if '-*-' in s or s.lower() == '@echo off':
            continue
        if s.startswith('<!--'):
            while '-->' not in s and i < len(lines):
                s = lines[i]
                i += 1
            continue
        if s.startswith('#'):
            text = s.lstrip('#').strip()
            if text and not s.startswith('##'):
                return text
            continue
        for quote in ('"""', "'''"):
            if s.startswith(quote):
                rest = s[3:].strip()
                if quote in rest:
                    return rest.split(quote)[0].strip()
                if rest:
                    return rest
                while i < len(lines):
                    nxt = lines[i].strip().split(quote)[0].strip()
                    i += 1
                    if nxt:
                        return nxt
                return ''
        if s.startswith('//'):
            return s[2:].strip()
        if s.lower().startswith('rem ') or s.startswith('::'):
            return s[3:].strip() if s.lower().startswith('rem') else s[2:].strip()
        return ''
    return ''


def _owner_table(text):
    """(domain, owner) rows of the first table headed '| Domain | Owner |'."""
    rows, inside = [], False
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith('|'):
            if inside:
                break
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if not inside:
            inside = [c.lower() for c in cells[:2]] == ['domain', 'owner']
        elif len(cells) >= 2 and cells[0] and not set(cells[0]) <= set('-: '):
            rows.append((cells[0], cells[1]))
    return rows


def _norm(text):
    return ' '.join(text.lower().split())


def _owner_row(rows, key, rel):
    """The one row whose domain is KEY or starts with KEY's words."""
    want = _norm(key)
    found = [r for r in rows if _norm(r[0]) == want] or [
        r for r in rows if _norm(r[0]).startswith(want)
        and not _norm(r[0])[len(want)].isalnum()]
    if not found:
        raise ValueError(f'no ownership-table row in {rel} starts with {key!r}; '
                         f'reword the owner_ref key or restore the row')
    if len(found) > 1:
        raise ValueError(f"{key!r} matches {len(found)} ownership-table rows in {rel}; "
                         f"use more of the domain's first words")
    return found[0]


# ---------------------------------------------------------------- registry

class Absent(ValueError):
    """A plugin source not installed on this device: a note, not a diagnostic."""


def _registry(fingerprints):
    """Load the plugin registry (read-only, <= AUX_LIMIT); return its plugins map."""
    path = Path(REGISTRY)
    data, fp = _file_state(path, AUX_LIMIT)
    fingerprints[_key(path)] = fp
    if data is None and not os.path.lexists(path):
        raise Absent(f'not installed: no plugin registry at {path}')
    if data is None:
        raise ValueError(f'plugin registry missing or unreadable: {path}')
    if len(data) > AUX_LIMIT:
        raise ValueError(f'plugin registry exceeds {AUX_LIMIT} bytes')
    try:
        doc = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        raise ValueError('plugin registry is not valid JSON')
    plugins = doc.get('plugins') if isinstance(doc, dict) else None
    if not isinstance(plugins, dict):
        raise ValueError('plugin registry has no "plugins" object')
    return plugins


def _plugin_root(root, key, plugins):
    """Pick the one install for this workspace: local > project > user, never first-of-many."""
    records = plugins.get(key)
    if isinstance(records, dict):
        records = [records]
    if records is None:
        raise Absent(f'not installed: plugin {key!r} not in registry')
    if not isinstance(records, list):
        raise ValueError(f'plugin {key!r} not in registry')
    root_real = os.path.normcase(os.path.realpath(root))
    ranked = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        scope, project = rec.get('scope'), rec.get('projectPath')
        if scope not in PLUGIN_RANK:
            continue
        if project is None:
            if scope != 'user':
                continue
        elif not isinstance(project, str) or not os.path.isabs(project) or \
                os.path.normcase(os.path.realpath(project)) != root_real:
            continue
        ranked.setdefault(PLUGIN_RANK[scope], []).append(rec)
    if not ranked:
        raise ValueError(f'plugin {key!r} has no install for this workspace or user scope')
    winners = ranked[min(ranked)]
    if len(winners) > 1:
        raise ValueError(f'plugin {key!r} is ambiguous: {len(winners)} installs '
                         f'at {winners[0]["scope"]!r} scope')
    install = winners[0].get('installPath')
    if not isinstance(install, str) or not os.path.isabs(install):
        raise ValueError(f'plugin {key!r} installPath is not an absolute path')
    if not os.path.isdir(install):
        raise ValueError(f'plugin {key!r} installPath does not exist')
    return Path(install)


# ---------------------------------------------------------------- building

def _source_spec(src):
    if not isinstance(src, dict):
        raise ValueError('source is not an object')
    unknown = sorted(set(src) - set(SOURCE_FIELDS) - set(SOURCE_OPTIONAL))
    if unknown:
        raise ValueError(f'unknown source fields {unknown}')
    for field in SOURCE_FIELDS:
        if not isinstance(src.get(field), str) or not src[field].strip():
            raise ValueError(f'source field {field!r} must be a non-empty string')
    for field in SOURCE_OPTIONAL:
        if field in src and not isinstance(src[field], str):
            raise ValueError(f'source field {field!r} must be a string')
    for field in ('collection', 'kind'):
        if not IDENT.match(src[field]):
            raise ValueError(f'invalid {field} {src[field]!r}')
    pattern = src['pattern']
    parts = pattern.split('/')
    if ('\\' in pattern or pattern.startswith('/') or DRIVE.match(pattern)
            or any(p in ('', '.', '..') for p in parts)
            or any('**' in p and p != '**' for p in parts) or parts[-1] == '**'):
        raise ValueError(f'unsupported pattern {pattern!r}')
    collapsed = []
    for p in parts:
        if not (p == '**' and collapsed and collapsed[-1] == '**'):
            collapsed.append(p)
    mode = src.get('mode', DEFAULT_MODE)
    if mode not in MODES:
        raise ValueError(f'unsupported mode {mode!r}; expected one of {list(MODES)}')
    spec = {f: src[f] for f in SOURCE_FIELDS}
    spec['scope'] = _rel_path(src['scope'], 'scope')
    spec['mode'] = mode
    spec['category'] = src.get('category', '').strip()
    spec['parts'] = collapsed
    return spec


def _source_base(root, raw_root, registry, fingerprints):
    """Resolve a source root: root-relative, absolute inside the root, or registry plugin."""
    if raw_root.startswith(PLUGIN_PREFIX):
        key, _, sub = raw_root[len(PLUGIN_PREFIX):].partition('/')
        if not PLUGIN_KEY.match(key):
            raise ValueError(f'invalid plugin key {key!r}')
        if 'plugins' not in registry:
            try:
                registry['plugins'] = (_registry(fingerprints), None)
            except ValueError as exc:
                registry['plugins'] = (None, exc)
        plugins, error = registry['plugins']
        if error:
            raise type(error)(str(error))
        base = _plugin_root(root, key, plugins)
        rel = _rel_path(sub, 'plugin subpath') if sub else '.'
        return base if rel == '.' else base / rel
    if os.path.isabs(raw_root) or DRIVE.match(raw_root):
        base = Path(os.path.abspath(raw_root))
        if not _inside(base, root):
            raise ValueError(f'absolute root {raw_root!r} is outside the workspace; '
                             f'external roots need a {PLUGIN_PREFIX} registry reference')
        return base
    rel = _rel_path(raw_root, 'root')
    base = root if rel == '.' else root / rel
    try:
        present = base.is_dir()
    except OSError:
        return base  # The caller records inaccessible roots as diagnostics.
    if not present:
        manifest = root / 'Harness/repos.txt'
        data, state = _file_state(manifest, AUX_LIMIT)
        if data is not None and len(data) <= AUX_LIMIT:
            fingerprints[_key(manifest)] = state
            try:
                resolved = base.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                resolved = rel
            for line in data.decode('utf-8').splitlines():
                if not line or line.startswith('#'):
                    continue
                pinned = _rel_path(line.split('\t')[0], 'pinned root')
                if resolved == pinned or resolved.startswith(pinned + '/'):
                    fingerprints[_key(base)] = _node(base)
                    raise Absent('optional pinned source not fetched: ' + pinned)
    return base


def _resolve_owner(root, ref, cache, fingerprints, diagnostics, label):
    file_part, sep, cell = ref.partition('|')
    cell = cell.strip()
    if not sep or not cell:
        diagnostics.append(f'{label}: owner_ref {ref!r} is not "file|cell"')
        return None
    try:
        rel = _rel_path(file_part, 'owner_ref file')
    except ValueError as exc:
        diagnostics.append(f'{label}: {exc}')
        return None
    if rel not in cache:
        path = root / rel
        data, fp = _file_state(path, AUX_LIMIT)
        fingerprints[_key(path)] = fp
        if data is None:
            cache[rel] = (None, 'owner file missing or unreadable')
        elif len(data) > AUX_LIMIT:
            cache[rel] = (None, 'owner file too large')
        else:
            try:
                rows = _owner_table(data.decode('utf-8'))
                cache[rel] = (rows, None) if rows else (
                    None, "no ownership table (a '| Domain | Owner |' header)")
            except UnicodeDecodeError:
                cache[rel] = (None, 'owner file is not UTF-8')
    table, error = cache[rel]
    if error:
        diagnostics.append(f'{label}: {error}: {rel}')
        return None
    try:
        domain, owner = _owner_row(table, cell, rel)
    except ValueError as exc:
        diagnostics.append(f'{label}: {exc}')
        return None
    if not owner:
        diagnostics.append(f'{label}: the owner cell of row {domain!r} in {rel} is empty')
        return None
    return owner


def _match(base, parts, fingerprints, diagnostics, label):
    """Glob below base; '**' spans zero or more real (non-link) directories.

    Every listed directory is fingerprinted so added/deleted files mark the
    index stale. Linked child directories are never traversed, which keeps
    the walk inside base and free of cycles; only base itself may be a link.
    """
    found, notes, seen, listings = set(), [], set(), {}
    base_real = os.path.realpath(base)
    stack = [(Path(base), 0)]
    while stack:
        directory, i = stack.pop()
        dkey = _key(directory)
        if (dkey, i) in seen:
            continue
        seen.add((dkey, i))
        part = parts[i]
        if part == '**':
            stack.append((directory, i + 1))
        if dkey not in listings:
            if len(listings) >= MAX_DIRS:
                notes.append(f'{label}: more than {MAX_DIRS} directories; traversal stopped')
                break
            items, fp = _dir_state(directory)
            fingerprints[dkey] = fp
            if items is None:
                notes.append(f'{label}: cannot list {directory}')
            listings[dkey] = items or []
        last = i == len(parts) - 1
        for item in listings[dkey]:
            hidden = item.name.startswith('.')
            if part == '**':
                if hidden:
                    continue
            elif not fnmatch.fnmatchcase(item.name, part) or (
                    hidden and not part.startswith('.')):
                continue
            path = Path(item.path)
            try:
                link = _is_link(path)
                if link and not os.path.exists(path):
                    fingerprints[_key(path)] = _node(path)
                    if part != '**':  # the next segment reports it if it matters
                        notes.append(f'{label}: broken link {path}')
                elif part == '**' or not last:
                    if not item.is_dir():
                        continue
                    if link:
                        fingerprints[_key(path)] = _node(path)
                        notes.append(f'{label}: linked directory not traversed {path}')
                        continue
                    stack.append((path, i if part == '**' else i + 1))
                elif item.is_file():
                    if link and not _inside(os.path.realpath(path), base_real):
                        fingerprints[_key(path)] = _node(path)
                        notes.append(f'{label}: link escapes source root {path}')
                        continue
                    found.add(path)
            except OSError as exc:
                fingerprints[_key(path)] = _node(path)
                notes.append(f'{label}: cannot stat {path} ({type(exc).__name__})')
    diagnostics.extend(dict.fromkeys(notes))
    return sorted(found)


def _entry(root, spec, base, path, owner, yaml, loader, fingerprints, diagnostics):
    shown = _display(root, path)
    data, fp = _file_state(path, READ_LIMIT)
    fingerprints[_key(path)] = fp
    if data is None:
        diagnostics.append(f'{shown}: unreadable; excluded')
        return None
    # Only the leading READ_LIMIT bytes are parsed: metadata must fit there,
    # bodies may be any size.
    truncated = len(data) > READ_LIMIT
    if truncated:
        data = data[:READ_LIMIT]
    try:
        text = codecs.getincrementaldecoder('utf-8')().decode(data, final=not truncated)
    except UnicodeDecodeError:
        diagnostics.append(f'{shown}: not UTF-8; excluded')
        return None
    text = text.lstrip('\ufeff').replace('\r\n', '\n')
    if truncated:
        text = text[:text.rfind('\n') + 1]  # drop the partial last line
    try:
        meta, body = _front_matter(text, lambda s: yaml.load(s, Loader=loader), truncated)
    except (yaml.YAMLError, ValueError, TypeError, RecursionError) as exc:
        first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
        diagnostics.append(f'{shown}: invalid front matter: {first}')
        return None
    kind = spec['kind']
    if meta is None and kind in ('skill', 'agent'):
        diagnostics.append(f'{shown}: missing front matter; excluded')
        return None
    has_meta = meta is not None
    meta = meta or {}
    for field in ('name', 'description', 'category'):
        if field in meta and not isinstance(meta[field], str):
            diagnostics.append(f'{shown}: front matter {field!r} must be a string')
            return None
    default = path.parent.name if kind == 'skill' else path.stem
    name = meta.get('name', '').strip() or default
    if not NAME.match(name):
        diagnostics.append(f'{shown}: invalid name {name!r}')
        return None
    purpose = ' '.join(meta.get('description', '').split())
    if not purpose:
        if kind == 'skill':
            diagnostics.append(f'{shown}: skill has no description; excluded')
            return None
        purpose = _summary(body)
    if truncated and not has_meta and not purpose:
        diagnostics.append(f'{shown}: exceeds {READ_LIMIT} bytes with no recognizable '
                           f'leading metadata; excluded')
        return None
    category = meta.get('category', '').strip() or spec['category']
    parts = Path(shown).parts if _inside(path, root) else path.relative_to(base).parts
    return {
        'id': f"{spec['collection']}:{kind}:{name}", 'name': name, 'kind': kind,
        'collection': spec['collection'], 'purpose': purpose, 'category': category,
        'path': shown, 'owner_ref': spec['owner_ref'], 'owner': owner,
        'scope': spec['scope'], 'mode': spec['mode'], 'aliases': [],
        'exclusions': [], 'source_present': True, 'configured_clients': [],
        'runtime_status': 'unknown',
        'unfinished': any(p.lower() in IN_PROGRESS for p in parts),
    }


def _policy_changes(override):
    if not isinstance(override, dict):
        raise ValueError('override is not an object')
    unknown = sorted(set(override) - set(POLICY_FIELDS))
    if unknown:
        raise ValueError(f'unsupported override fields {unknown}')
    changes = {}
    for field, value in override.items():
        if field in ('aliases', 'exclusions'):
            if not isinstance(value, list) or not all(
                    isinstance(v, str) and v.strip() for v in value):
                raise ValueError(f'{field} must be a list of non-empty strings')
            if field == 'exclusions':
                changes[field] = sorted({_rel_path(v, 'exclusion') for v in value})
            else:
                changes[field] = sorted({' '.join(v.split()) for v in value})
        elif not isinstance(value, str):
            raise ValueError(f'{field} must be a string')
        elif field == 'scope':
            changes[field] = _rel_path(value, 'scope')
        elif field == 'mode':
            if value not in MODES:
                raise ValueError(f'unsupported mode {value!r}; expected one of {list(MODES)}')
            changes[field] = value
        else:
            changes[field] = ' '.join(value.split())
    return changes


def _apply_policy(found, policy, diagnostics, notes, absent):
    if not isinstance(policy, dict):
        diagnostics.append('policy is not an object; ignored')
        return
    extra = sorted(set(policy) - {'entries'})
    if extra:
        diagnostics.append(f'policy has unsupported keys {extra}')
    entries = policy.get('entries', {})
    if not isinstance(entries, dict):
        diagnostics.append('policy "entries" is not an object; ignored')
        return
    for eid in sorted(entries):
        if eid not in found and eid.startswith(tuple(absent)):
            notes.append(f'policy for {eid} waits for its plugin')
            continue
        if eid not in found:
            diagnostics.append(f'policy references unknown entry {eid}')
            continue
        try:
            found[eid].update(_policy_changes(entries[eid]))
        except ValueError as exc:
            diagnostics.append(f'policy for {eid} ignored: {exc}')


def build_index(root: Path, sources: list, policy: dict) -> dict:
    import yaml  # lazy: queries must never need the parser
    loader = _strict_loader(yaml)
    root = Path(os.path.abspath(root))
    diagnostics, fingerprints, found, owners, registry = [], {}, {}, {}, {}
    notes, absent = [], []
    if not isinstance(sources, list):
        diagnostics.append('sources is not a list; no sources indexed')
        sources = []
    for pos, src in enumerate(sources):
        label = f'source[{pos}]'
        try:
            spec = _source_spec(src)
        except ValueError as exc:
            diagnostics.append(f'{label}: {exc}')
            continue
        label = f"{label} {spec['collection']}:{spec['kind']}"
        owner = _resolve_owner(root, spec['owner_ref'], owners, fingerprints,
                               diagnostics, label)
        try:
            base = _source_base(root, spec['root'], registry, fingerprints)
        except Absent as exc:
            notes.append(f'{label}: skipped, {exc}')
            absent.append(f"{spec['collection']}:{spec['kind']}:")
            continue
        except ValueError as exc:
            diagnostics.append(f'{label}: {exc}')
            continue
        try:
            is_dir = base.is_dir()
        except OSError:  # e.g. a Windows file symlink to a directory
            is_dir = False
        if not is_dir:
            fingerprints[_key(base)] = _node(base)
            diagnostics.append(f"{label}: root {spec['root']!r} missing or not a directory")
            continue
        for path in _match(base, spec['parts'], fingerprints, diagnostics, label):
            entry = _entry(root, spec, base, path, owner, yaml, loader,
                           fingerprints, diagnostics)
            if entry is None:
                continue
            prior = found.get(entry['id'])
            if prior is not None:
                diagnostics.append(f"duplicate id {entry['id']}: {entry['path']} "
                                   f"ignored, kept {prior['path']}")
                continue
            found[entry['id']] = entry
    _apply_policy(found, policy, diagnostics, notes, absent)
    router = [{'file': rel, 'domain': domain, 'owner': owner}
              for rel in sorted(owners) for domain, owner in owners[rel][0] or ()]
    return {'schema': SCHEMA,
            'fingerprints': dict(sorted(fingerprints.items())),
            'entries': [found[k] for k in sorted(found)],
            'diagnostics': diagnostics, NOTES: notes, 'router': router}


# ---------------------------------------------------------------- validation

def _string_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _structure_errors(index):
    if not isinstance(index, dict):
        return ['index is not an object']
    errors = []
    if set(index) - {NOTES} != INDEX_KEYS:
        errors.append(f'index keys must be {sorted(INDEX_KEYS)}, and optionally {NOTES!r}')
    if NOTES in index and not _string_list(index[NOTES]):
        errors.append(f'{NOTES} must be a list of strings')
    schema = index.get('schema')
    if isinstance(schema, bool) or schema != SCHEMA:
        errors.append(f'unsupported schema {schema!r}')
    fps = index.get('fingerprints')
    if not isinstance(fps, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in fps.items()):
        errors.append('fingerprints must map strings to strings')
    if not _string_list(index.get('diagnostics')):
        errors.append('diagnostics must be a list of strings')
    router = index.get('router')
    if not isinstance(router, list) or not all(
            isinstance(r, dict) and all(isinstance(r.get(f), str) for f in ROUTER_FIELDS)
            for r in router):
        errors.append('router must be a list of {file, domain, owner} strings')
    entries = index.get('entries')
    if not isinstance(entries, list):
        return errors + ['entries must be a list']
    ids = []
    for pos, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f'entry {pos} is not an object')
            continue
        bad = [f for f, t in ENTRY_FIELDS.items()
               if f not in entry or not isinstance(entry[f], t)
               or (t is not bool and isinstance(entry[f], bool))]
        if bad:
            errors.append(f'entry {pos} has missing/invalid fields {bad}')
            continue
        eid = entry['id']
        ids.append(eid)
        if eid != f"{entry['collection']}:{entry['kind']}:{entry['name']}":
            errors.append(f'entry {eid} id does not match collection:kind:name')
        for field in ('aliases', 'exclusions', 'configured_clients'):
            if not _string_list(entry[field]):
                errors.append(f'entry {eid} {field} must be a list of strings')
        if entry['runtime_status'] != 'unknown':
            errors.append(f'entry {eid} claims runtime status; must be "unknown"')
        if entry['mode'] not in MODES:
            errors.append(f'entry {eid} has unsupported mode {entry["mode"]!r}')
        try:
            if _rel_path(entry['scope'], 'scope') != entry['scope']:
                errors.append(f'entry {eid} scope is not normalized')
        except ValueError as exc:
            errors.append(f'entry {eid}: {exc}')
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f'duplicate ids {dupes}')
    if ids != sorted(ids):
        errors.append('entries are not sorted by id')
    return errors


def validate_index(index) -> list:
    errors = _structure_errors(index)
    diagnostics = index.get('diagnostics') if isinstance(index, dict) else None
    if isinstance(diagnostics, list) and diagnostics:
        errors.append(f'index has {len(diagnostics)} diagnostic(s); not healthy')
    return errors


# ---------------------------------------------------------------- search

def _eligibility(entry, project, client):
    if entry['mode'] not in MODES or entry['owner'] is None:
        return None
    if not _within(project, entry['scope']):
        return None
    if any(_within(project, ex) for ex in entry['exclusions']):
        return None
    where = ('scope "." applies everywhere' if entry['scope'] == '.'
             else f"project {project!r} is within scope {entry['scope']!r}")
    parts = ['UNFINISHED: in progress, not production-ready'] if entry['unfinished'] else []
    parts += [where, f"owner {entry['owner']!r}", f"mode {entry['mode']}",
              f'client {client!r} exposure not verified (runtime unknown)']
    return '; '.join(parts)


def search(index, query, project, client, limit=5):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f'limit must be an integer 1..{MAX_LIMIT}')
    project = _rel_path(project, 'project')
    if not isinstance(client, str) or not client.strip():
        raise ValueError('client must be a non-empty string')
    if not isinstance(query, str):
        raise ValueError('query must be a string')
    errors = _structure_errors(index)
    if errors:
        raise ValueError('invalid index: ' + errors[0])
    terms = [t for t in dict.fromkeys(_tokens(query)) if t not in STOP_WORDS]
    if not terms:
        return []
    phrase = ' '.join(query.lower().split())
    hits = []
    for entry in index['entries']:
        reason = _eligibility(entry, project, client)
        if reason is None:
            continue
        fields = {'name': set(_tokens(entry['name'])),
                  'aliases': set(_tokens(' '.join(entry['aliases']))),
                  'purpose': set(_tokens(entry['purpose'])),
                  'category': set(_tokens(entry['category']))}
        score, matched = 0, set()
        for term in terms:
            for field, weight in WEIGHTS:
                if term in fields[field]:
                    score += weight
                    matched.add(term)
        if not matched:
            continue
        if phrase == entry['name'].lower() or phrase in (a.lower() for a in entry['aliases']):
            score += EXACT_BONUS
        hits.append({'entry': copy.deepcopy(entry), 'score': score,
                     'matched_terms': sorted(matched), 'eligibility_reason': reason})
    hits.sort(key=lambda h: (-h['score'], h['entry']['id']))
    return hits[:limit]


# ---------------------------------------------------------------- pick

# Words that name no task: chit-chat, pronouns, auxiliaries, the workspace itself.
PICK_STOP = STOP_WORDS | frozenset(
    'i me my mine we us our you your he she they them their its these those '
    'am are was were been being do does did done doing have has had having '
    'can could would should will shall may might must let what which who whom whose '
    'when where why how here there then than so very really much more most some any '
    'all each every no not nothing else only just also too again still now today later '
    'please thanks thank hi hello hey ok okay yes yeah good great nice cool fine sure '
    'well want need like get got make made help task anything something dev '
    'first second third non one two three new other another same many few last '
    'find show see look use using used work way thing things go going come take '
    'put keep set up'.split())
SUFFIXES = ('ings', 'ing', 'ions', 'ion', 'ers', 'er', 'ies', 'es', 'ed', 's', 'e')
PICK_FIELDS = (('name', 3.0), ('aliases', 3.0), ('category', 2.0), ('purpose', 1.0))
NAMED_BOOST = 3.0    # a router row whose owner cell names the entry in backticks
MEMBER_BOOST = 1.0   # the row the entry's owner_ref points at
PICK_MIN = 12.0      # an entry below this lexical score is never offered
PICK_SHARE = 0.3     # nor one below this share of the best pick's score
PICK_WORDS = 2       # nor one matching fewer distinct prompt words, unless a trigger fired
BACKTICKS = re.compile(r'`([^`]+)`')


def _stem(word):
    """Crude, deterministic stemming: one common suffix off, then six letters."""
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[:-len(suffix)] + ('y' if suffix == 'ies' else '')
            break
    return word[:6]


def _stems(text):
    stems = {_stem(t) for t in _tokens(text)
             if len(t) > 1 and not t.isdigit() and t not in PICK_STOP}
    return stems - PICK_STOP  # 'showing' stems to the stop word 'show'


def _router_rows(index):
    """{file: [(domain, domain stems, names the owner cell puts in backticks)]}."""
    rows = {}
    for r in index['router']:
        names = {w for w in (span.split()[0].rstrip('/').lower()
                             for span in BACKTICKS.findall(r['owner']) if span.split())
                 if '/' not in w}
        rows.setdefault(r['file'], []).append((r['domain'], _stems(r['domain']), names))
    return rows


def _weigh(terms, docs, weights):
    """Per doc: {term: the best weight among the fields that hold the term}."""
    out = []
    for fields in docs:
        hits = {}
        for t in terms:
            best = max((weight for field, weight in weights if t in fields[field]), default=0)
            if best:
                hits[t] = best
        out.append(hits)
    return out


def _idf_scores(hits_per_doc):
    """Sum each doc's hits, weighted by how few docs a term reaches."""
    df = {}
    for hits in hits_per_doc:
        for t in hits:
            df[t] = df.get(t, 0) + 1
    n = len(hits_per_doc) + 1
    return [sum(math.log(n / (df[t] + 0.5)) * w for t, w in hits.items())
            for hits in hits_per_doc]


def pick(index, text, project='.', top=3):
    """Rank eligible entries for a free-text prompt; [] when none is relevant enough.

    An entry scores on its name, triggers (policy aliases), category and
    purpose, each word weighted by how rare it is among the entries; then the
    router adds its word: the best-matching row that names the entry in its
    owner cell (NAMED_BOOST) or that its owner_ref points at (MEMBER_BOOST),
    scored on the row's domain words by their rarity among the rows. So the
    table's owner outranks lexical noise. Scores are lexical relevance, never
    safety or confidence; nothing is run.
    """
    if isinstance(top, bool) or not isinstance(top, int) or not 1 <= top <= MAX_LIMIT:
        raise ValueError(f'top must be an integer 1..{MAX_LIMIT}')
    if not isinstance(text, str):
        raise ValueError('text must be a string')
    project = _rel_path(project, 'project')
    errors = _structure_errors(index)
    if errors:
        raise ValueError('invalid index: ' + errors[0])
    terms = _stems(text)
    if not terms:
        return []
    entries = [e for e in index['entries'] if _eligibility(e, project, 'pick') is not None]
    by_file = _router_rows(index)
    rows = [r for file_rows in by_file.values() for r in file_rows]
    docs = []
    for e in entries:
        # A trigger counts only when every one of its words is in the prompt.
        fired = [s for s in map(_stems, e['aliases']) if s and s <= terms]
        docs.append({'name': _stems(e['name']), 'aliases': set().union(*fired),
                     'category': _stems(e['category']), 'purpose': _stems(e['purpose'])})
    entry_hits = _weigh(terms, docs, PICK_FIELDS)
    row_hits = _weigh(terms, [{'domain': r[1]} for r in rows], (('domain', 1.0),))
    row_match = {r[0]: (score, hits)
                 for r, score, hits in zip(rows, _idf_scores(row_hits), row_hits)}
    own = {}
    picks = []
    for e, doc, hits, score in zip(entries, docs, entry_hits, _idf_scores(entry_hits)):
        ref = e['owner_ref']
        if ref not in own:
            rel, _, key = ref.partition('|')
            try:
                own[ref] = _owner_row(by_file.get(rel, []), key, rel)[0]
            except ValueError:
                own[ref] = None
        boost, route, by_name = 0.0, None, False
        for domain, _, names in rows:
            named = e['name'].lower() in names or e['collection'] in names
            weight = NAMED_BOOST if named else MEMBER_BOOST if domain == own[ref] else 0.0
            if weight * row_match[domain][0] > boost:
                boost, route, by_name = weight * row_match[domain][0], domain, named
        matched = set(hits) | set(row_match[route][1] if route else ())
        # One matching word ("the format is good", "the licence check") is not enough
        # evidence for a pick, unless it fired a curated trigger. A row's words count
        # only when the row names the entry: an owner's row ("security scanning")
        # says nothing of each ECC command that shares it.
        evidence = set(hits) | set(row_match[route][1] if by_name else ())
        if score + boost >= PICK_MIN and (len(evidence) >= PICK_WORDS or doc['aliases']):
            picks.append({'entry': copy.deepcopy(e), 'score': round(score + boost, 2),
                          'matched_terms': sorted(matched), 'route': route})
    picks.sort(key=lambda p: (-p['score'], p['entry']['id']))
    best = picks[0]['score'] if picks else 0
    return [p for p in picks if p['score'] >= best * PICK_SHARE][:top]


# ------------------------------------------------------------ eval-picks

MARK_TOTAL = re.compile(r'(\d+) of (?:the )?(\d+) (?:overall|positive)', re.I)
MARK_COLD = re.compile(r'(\d+) of (?:the )?(\d+) marked cold_start', re.I)
MARK_REVERSE = re.compile(r'\b(?:both|every|all)\b[^.;]*\breverse', re.I)
NEGATIVE = ('none', 'none-in-dev')


def eval_picks(index, doc):
    """Grade a frozen prompt set by its own pass mark.

    A prompt passes when any expected name is a case-insensitive substring
    of a top-3 pick's id or path; 'none'/'none-in-dev' prompts pass when
    nothing is picked and are reported, not counted. Raises ValueError when
    the set or its pass mark cannot be read.
    """
    prompts = doc.get('prompts') if isinstance(doc, dict) else None
    if not isinstance(prompts, list) or not prompts:
        raise ValueError('the set has no "prompts" list')
    mark = str(doc.get('_pass_mark') or doc.get('_frozen') or '')
    total = MARK_TOTAL.search(mark)
    if not total:
        raise ValueError('no pass mark ("N of M overall" or "N of the M positive prompts")')
    rows = []
    for p in prompts:
        if not isinstance(p, dict) or not isinstance(p.get('q'), str) or not (
                isinstance(p.get('any'), list) and p['any']):
            raise ValueError(f'malformed prompt {p!r:.80}')
        found = pick(index, p['q'], '.', 3)
        got = [f"{f['entry']['id']} {f['entry']['path']}".lower() for f in found]
        negative = p['any'][0] in NEGATIVE
        ok = not found if negative else any(
            str(name).lower() in g for name in p['any'] for g in got)
        rows.append({'q': p['q'], 'any': p['any'], 'passed': ok, 'negative': negative,
                     'cold_start': bool(p.get('cold_start')) and not negative,
                     'reverse': not negative and (bool(p.get('reverse')) or 'reverse'
                                                  in str(p.get('area', '')).lower()),
                     'picks': [f['entry']['id'] for f in found]})
    groups = {g: [r['passed'] for r in rows if r[g] and (g == 'negative' or not r['negative'])]
              for g in ('negative', 'cold_start', 'reverse')}
    groups['overall'] = [r['passed'] for r in rows if not r['negative']]
    need, stated = int(total.group(1)), int(total.group(2))
    marks = {'overall': need}
    if stated != len(groups['overall']):
        raise ValueError(f'the pass mark counts {stated} prompts; the set holds '
                         f"{len(groups['overall'])} that expect a pick")
    cold = MARK_COLD.search(mark)
    if cold:
        if int(cold.group(2)) != len(groups['cold_start']):
            raise ValueError(f'the pass mark counts {cold.group(2)} cold_start prompts; '
                             f"the set marks {len(groups['cold_start'])}")
        marks['cold_start'] = int(cold.group(1))
    if MARK_REVERSE.search(mark):
        marks['reverse'] = len(groups['reverse'])
    passed = all(sum(groups[g]) >= n for g, n in marks.items())
    return {'rows': rows, 'groups': {g: [sum(v), len(v)] for g, v in groups.items()},
            'marks': marks, 'passed': passed}


# ---------------------------------------------------------------- coverage

# A clone that is data rather than a tool is covered by the entry that reads it.
# (The owner's book PDFs are a personal clone, not in repos.txt, so never held.)
COVERAGE_MAP = {
}
MCP_TOML = re.compile(r'^\s*\[mcp_servers\.([A-Za-z0-9_-]+)\]\s*$', re.M)
# bootstrap registers dev's MCP servers for the user: 'for server in "<name> <launcher> <wait>" ...; do'.
MCP_BOOTSTRAP = re.compile(r'^for server in ((?:"[^"]*"\s*)+); do', re.M)


def _children(folder):
    try:
        return sorted(p for p in Path(folder).iterdir() if not p.name.startswith('.'))
    except OSError:
        return []


def _real(path):
    return os.path.normcase(os.path.realpath(path))


def _names(path):
    """The item's own name and, for a link, the name it points at (even dangling)."""
    names = {path.stem if path.suffix == '.md' else path.name}
    if _is_link(path):
        try:
            target = Path(os.readlink(path).replace('\\', '/').rstrip('/'))
            names.add(target.stem if target.suffix == '.md' else target.name)
        except OSError:
            pass
    return names


def _text(path):
    try:
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return ''


def held(root):
    """Everything dev holds that needs an entry: (kind, label, names, real path)."""
    root = Path(root)
    items = []
    for folder in ('.claude/skills', '.agents/skills'):
        for p in _children(root / folder):
            # A link first: is_dir() raises on a Windows file link to a directory.
            if _is_link(p) or p.is_dir():
                items.append(('skill', f'{folder}/{p.name}', _names(p), _real(p)))
    for p in _children(root / 'Harness/bin'):
        if p.is_file():
            items.append(('command', f'Harness/bin/{p.name}', _names(p), _real(p)))
    for p in _children(root / '.claude/agents'):
        if p.suffix == '.md':
            items.append(('agent', f'.claude/agents/{p.name}', _names(p), _real(p)))
    try:
        servers = json.loads(_text(root / '.mcp.json') or '{}').get('mcpServers', {})
    except (ValueError, AttributeError):
        servers = {}
    for name in sorted(servers if isinstance(servers, dict) else {}):
        items.append(('mcp', f'.mcp.json mcpServers.{name}', {name}, None))
    for name in sorted(set(MCP_TOML.findall(_text(root / '.codex/config.toml')))):
        items.append(('mcp', f'.codex/config.toml mcp_servers.{name}', {name}, None))
    loop = MCP_BOOTSTRAP.search(_text(root / 'Harness/bootstrap.sh'))
    for name in sorted(set(re.findall(r'"(\S+)', loop.group(1)))) if loop else ():
        items.append(('mcp', f'Harness/bootstrap.sh mcp {name}', {name}, None))
    for line in _text(root / 'Harness/repos.txt').splitlines():
        rel = line.split('\t', 1)[0].strip()
        if rel and not rel.startswith('#'):
            items.append(('clone', rel, set(), _real(root / rel)))
    return items


def coverage(root, index):
    """Return (items, orphans): an item is covered by an entry of its kind with
    the same name or the same file; a clone by any entry inside it."""
    root = Path(os.path.abspath(root))
    names, files, reals = {}, {}, []
    for e in index['entries']:
        real = _real(root / e['path'])
        reals.append(real)
        names.setdefault(e['kind'], set()).add(e['name'])
        files.setdefault(e['kind'], set()).update({real, os.path.dirname(real)})
    ids = {e['id'] for e in index['entries']}
    items = held(root)
    orphans = []
    for kind, label, item_names, real in items:
        if kind == 'clone':
            ok = COVERAGE_MAP.get(label) in ids or any(_inside(r, real) for r in reals)
        else:
            ok = bool(item_names & names.get(kind, set())) or real in files.get(kind, set())
        if not ok:
            orphans.append({'kind': kind, 'path': label})
    return items, orphans


# ---------------------------------------------------------------- CLI

class CliError(Exception):
    def __init__(self, code, message, exit_code=2, **extra):
        super().__init__(message)
        self.code, self.exit_code, self.extra = code, exit_code, extra


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError('bad_argument', f'{self.prog}: {message}')


def _load_json(path, limit, code):
    data, fp = _file_state(path, limit)
    if data is None:
        raise CliError(code, f'{path} missing or unreadable')
    if len(data) > limit:
        raise CliError(code, f'{path} exceeds {limit} bytes')
    try:
        return json.loads(data.decode('utf-8')), fp
    except (UnicodeDecodeError, ValueError) as exc:
        raise CliError(code, f'{path} is not valid JSON ({type(exc).__name__})')


def _current(key, recorded):
    kind = recorded.split(':', 1)[0]
    if kind in ('missing', 'node'):
        return _node(key)
    if kind in ('dir', 'unlistable'):
        return _dir_state(key)[1]
    if kind in ('file', 'unreadable'):
        try:
            limit = min(int(recorded.split(':')[1]), AUX_LIMIT)
        except (IndexError, ValueError):
            return 'unknown'
        return _file_state(key, limit)[1]
    return 'unknown'


def _stale(index):
    return [k for k, v in sorted(index['fingerprints'].items()) if _current(k, v) != v]


def _load_index(path):
    if not path.is_file():
        raise CliError('missing_index', f'index missing at {path}; run "library refresh"')
    try:
        index, _ = _load_json(path, INDEX_LIMIT, 'corrupt_index')
    except CliError as exc:
        raise CliError('corrupt_index',
                       f'index unreadable or corrupt ({exc}); run "library refresh"')
    errors = _structure_errors(index)
    if errors:
        raise CliError('corrupt_index',
                       f'index corrupt ({errors[0]}); run "library refresh"')
    return index


def _fresh_index(path):
    """Index usable for search/show: well-formed, fresh and without diagnostics."""
    index = _load_index(path)
    stale = _stale(index)
    if stale:
        raise CliError('stale_index', f'index stale ({len(stale)} changed source(s)); '
                       f'run "library refresh"', stale=stale)
    if index['diagnostics']:
        raise CliError('degraded_index',
                       f"index degraded ({len(index['diagnostics'])} diagnostic(s)); "
                       f'fix sources and run "library refresh"',
                       diagnostics=index['diagnostics'])
    return index


def _emit(args, payload, lines):
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for line in lines:
            print(line)


def _fail(as_json, exc):
    if as_json:
        payload = dict(exc.extra, status='error', error=exc.code, message=str(exc))
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f'error: {exc}', file=sys.stderr)
    return exc.exit_code


def _write_atomic(path, index):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(index, indent=2, sort_keys=True) + '\n'
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _cmd_refresh(args):
    manifests = [args.root / 'Harness' / 'library-sources.json',
                 args.root / 'Harness' / 'library-policy.json']
    sources, sources_fp = _load_json(manifests[0], AUX_LIMIT, 'manifest_error')
    policy, policy_fp = _load_json(manifests[1], AUX_LIMIT, 'manifest_error')
    if not isinstance(sources, list):
        raise CliError('manifest_error', 'library-sources.json must contain a list')
    if not isinstance(policy, dict):
        raise CliError('manifest_error', 'library-policy.json must contain an object')
    index = build_index(args.root, sources, policy)
    index['fingerprints'][_key(manifests[0])] = sources_fp
    index['fingerprints'][_key(manifests[1])] = policy_fp
    index['fingerprints'] = dict(sorted(index['fingerprints'].items()))
    problems = validate_index(index)
    _write_atomic(args.index, index)
    status = 'healthy' if not problems else 'degraded'
    lines = [f"wrote {args.index}: {len(index['entries'])} entries, "
             f"{len(index['diagnostics'])} diagnostics ({status})"]
    lines += [f'  diagnostic: {d}' for d in index['diagnostics']]
    lines += [f'  note: {n}' for n in index[NOTES]]
    lines += [f'  problem: {p}' for p in problems if not index['diagnostics']]
    _emit(args, {'status': status, 'index': str(args.index),
                 'entries': len(index['entries']), NOTES: index[NOTES],
                 'diagnostics': index['diagnostics'], 'problems': problems}, lines)
    return 0 if not problems else 1


def _cmd_check(args):
    index = _load_index(args.index)
    problems = validate_index(index)
    stale = _stale(index)
    problems += [f'stale fingerprint: {k}' for k in stale]
    status = 'ok' if not problems else 'unhealthy'
    lines = [f"index {status}: {len(index['entries'])} entries"]
    lines += [f'  diagnostic: {d}' for d in index['diagnostics']]
    lines += [f'  note: {n}' for n in index.get(NOTES, [])]
    lines += [f'  problem: {p}' for p in problems]
    _emit(args, {'status': status, 'entries': len(index['entries']),
                 NOTES: index.get(NOTES, []),
                 'diagnostics': index['diagnostics'], 'problems': problems}, lines)
    return 0 if not problems else 1


def _cmd_search(args):
    if not 1 <= args.limit <= MAX_LIMIT:
        raise CliError('bad_argument', f'limit must be an integer 1..{MAX_LIMIT}')
    index = _fresh_index(args.index)
    try:
        hits = search(index, args.query, args.project, args.client, args.limit)
    except ValueError as exc:
        raise CliError('bad_argument', str(exc))
    lines = [] if hits else ['no eligible matches']
    for n, hit in enumerate(hits, 1):
        e = hit['entry']
        lines.append(f"{n}. {e['id']} (score {hit['score']}) {e['purpose'][:120]}")
        lines.append(f"   path: {e['path']}; scope: {e['scope']}; "
                     f"{hit['eligibility_reason']}")
    _emit(args, hits, lines)
    return 0


def _usable_index(path):
    """A well-formed index plus warnings: pick still answers from a stale or degraded one."""
    index = _load_index(path)
    warnings = []
    stale = _stale(index)
    if stale:
        warnings.append(f'index stale ({len(stale)} changed source(s)); run "library refresh"')
    if index['diagnostics']:
        warnings.append(f"index degraded ({len(index['diagnostics'])} diagnostic(s)); "
                        f'run "library check"')
    return index, warnings


def _one_line(text, limit=120):
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 3].rsplit(' ', 1)[0] + '...'


def _project_of(root, cwd):
    """The working folder relative to the workspace root; '.' outside it."""
    try:
        return Path(os.path.abspath(cwd)).relative_to(root).as_posix() or '.'
    except ValueError:
        return '.'


def _cmd_pick(args):
    index, warnings = _usable_index(args.index)
    project = args.project if args.project is not None else _project_of(args.root, Path.cwd())
    try:
        picks = pick(index, args.text, project, args.top)
    except ValueError as exc:
        raise CliError('bad_argument', str(exc))
    if not args.json:
        for warning in warnings:
            print(f'warning: {warning}', file=sys.stderr)
    # Absolute, so the line works from any folder and in an agent's Read tool.
    files = [(args.root / p['entry']['path']).as_posix() for p in picks]
    payload = {'picks': [{'id': p['entry']['id'], 'purpose': p['entry']['purpose'],
                          'path': p['entry']['path'], 'file': f, 'mode': p['entry']['mode'],
                          'lexical_score': p['score'], 'matched_terms': p['matched_terms'],
                          'route': p['route']} for p, f in zip(picks, files)],
               'project': project, 'warnings': warnings}
    lines = [f"{n}. {p['entry']['id']} - {_one_line(p['entry']['purpose'])}" for n, p in enumerate(picks, 1)]
    if not args.no_path:
        lines = [f'{line} - {f}' for line, f in zip(lines, files)]
    _emit(args, payload, lines)
    return 0


def _cmd_eval_picks(args):
    index, warnings = _usable_index(args.index)
    doc, _ = _load_json(args.file, AUX_LIMIT, 'bad_set')
    try:
        result = eval_picks(index, doc)
    except ValueError as exc:
        raise CliError('bad_set', f'{args.file}: {exc}')
    lines = [f'warning: {w}' for w in warnings]
    for r in result['rows']:
        q = _one_line(r['q'], 80)
        lines.append(f"{'PASS' if r['passed'] else 'FAIL'}  {q}")
        if args.report or not r['passed']:
            lines.append(f"      expected {', '.join(r['any'])}; picked "
                         f"{', '.join(r['picks']) or 'nothing'}")
    names = {'overall': 'overall', 'cold_start': 'cold_start', 'reverse': 'reverse'}
    for group, label in names.items():
        if group in result['marks']:
            got, of = result['groups'][group]
            lines.append(f"{label}: {got} of {of} passed (mark {result['marks'][group]})")
    got, of = result['groups']['negative']
    if of:
        lines.append(f'negatives: {got} of {of} got no pick (reported, not counted)')
    lines.append(f"result: {'PASS' if result['passed'] else 'BELOW THE PASS MARK'}")
    _emit(args, dict(result, warnings=warnings), lines)
    return 0 if result['passed'] else 1


def _cmd_coverage(args):
    index = _load_index(args.index)
    stale = _stale(index)
    if stale:
        raise CliError('stale_index', f'index stale ({len(stale)} changed source(s)); '
                       f'run "library refresh"', stale=stale)
    items, orphans = coverage(args.root, index)
    status = 'ok' if not orphans else 'orphans'
    if orphans:
        lines = [f'coverage: {len(orphans)} of {len(items)} items have no library entry']
        lines += [f"  orphan: {o['kind']} {o['path']}" for o in orphans]
    else:
        lines = [f'coverage ok: {len(items)} items, each with a library entry']
    _emit(args, {'status': status, 'items': len(items), 'orphans': orphans}, lines)
    return 0 if not orphans else 1


def _cmd_show(args):
    index = _fresh_index(args.index)
    entry = next((e for e in index['entries'] if e['id'] == args.id), None)
    if entry is None:
        raise CliError('unknown_id', f'no entry {args.id!r}', exit_code=1)
    _emit(args, entry, [f'{k}: {entry[k]}' for k in sorted(entry)])
    return 0


def _parser():
    parser = _Parser(prog='library', description='Offline library index')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--index', type=Path, default=None)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('find', help='search Vercel using only approved generic keywords')
    p.add_argument('text')
    p.set_defaults(func=_cmd_find)
    p = sub.add_parser('refresh', help='rebuild the index from manifests')
    p.set_defaults(func=_cmd_refresh)
    p = sub.add_parser('search', help='search eligible entries')
    p.add_argument('query')
    p.add_argument('--project', default='.')
    p.add_argument('--client', default='codex')
    p.add_argument('--limit', type=int, default=5)
    p.set_defaults(func=_cmd_search)
    p = sub.add_parser('show', help='show one entry')
    p.add_argument('id')
    p.set_defaults(func=_cmd_show)
    p = sub.add_parser('check', help='validate and rehash the index')
    p.set_defaults(func=_cmd_check)
    p = sub.add_parser('coverage', help='list held skills, commands, agents, MCP '
                       'servers and clones that have no entry')
    p.set_defaults(func=_cmd_coverage)
    p = sub.add_parser('pick', help='suggest the entries that fit a free-text prompt; '
                       'prints nothing when none is relevant enough')
    p.add_argument('text')
    p.add_argument('--top', type=int, default=3)
    p.add_argument('--no-path', action='store_true',
                   help="leave out each entry's file; library show ID prints it")
    p.add_argument('--project', default=None,
                   help='project folder for scope (default: the working folder)')
    p.set_defaults(func=_cmd_pick)
    p = sub.add_parser('eval-picks', help='grade pick on a frozen prompt set by its pass mark')
    p.add_argument('file', type=Path)
    p.add_argument('--report', action='store_true', help='show the picks for every prompt')
    p.set_defaults(func=_cmd_eval_picks)
    for name in ('refresh', 'search', 'show', 'check', 'coverage', 'pick', 'find', 'eval-picks'):
        sub.choices[name].add_argument('--json', action='store_true')
    return parser


def _cmd_find(args):
    from vercel_find import discover
    lines = discover(args.text, args.root, cwd=Path.cwd())
    _emit(args, {'lines': lines}, lines)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    as_json = '--json' in argv  # before parsing succeeds, honour the raw flag
    try:
        args = _parser().parse_args(argv)
        as_json = args.json
        args.root = Path(os.path.abspath(args.root))
        if args.index is None:
            args.index = args.root / '.claude' / 'hooks' / 'library' / 'index.json'
        return args.func(args)
    except CliError as exc:
        return _fail(as_json, exc)
    except Exception as exc:  # no tracebacks: report and fail closed
        return _fail(as_json, CliError('internal_error', f'{type(exc).__name__}: {exc}'))


if __name__ == '__main__':
    raise SystemExit(main())
