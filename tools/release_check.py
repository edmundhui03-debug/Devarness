#!/usr/bin/env python3
"""Check tracked source and reachable history; report locations, never secret values."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVACY_SPEC = importlib.util.spec_from_file_location('publish_check', ROOT / 'Harness/publish-check.py')
PRIVACY = importlib.util.module_from_spec(PRIVACY_SPEC)
PRIVACY_SPEC.loader.exec_module(PRIVACY)
RULES = {
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'provider-key': re.compile(r'\bsk-(?:proj-|ant-api\d+-)?[A-Za-z0-9_-]{24,}\b'),
    'aws-key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential-url': re.compile(r'https?://[^\s/<>:@]+:[^\s/<>@]+@'),
    'literal-credential': re.compile(r'''(?ix)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|client[_-]?secret)\s*["']?\s*[:=]\s*["']([A-Za-z0-9_+/=-]{20,})["']'''),
}
PRIVATE_ROOTS = {'Projects', 'Books', 'Working', 'Setup', 'PRDs and Specs'}
PRIVATE_FILES = {'.env', 'auth.json', 'tokens.json', 'credentials.json', 'secrets.json', 'ntfy-topic', 'personal-repos.txt'}
PRIVATE_RUNTIME = ('.claude/hooks/task-recall.memo.json', '.claude/hooks/update-tools.lock',
                   '.claude/hooks/update-tools/')
PRIVATE_DASHBOARD = ('Harness/dashboard/', 'Harness/bin/dashboard',
                     'Harness/bin/taskboard', 'Harness/taskboard-zh-hk.json',
                     'Library/dashboard/', 'Library/bin/dashboard',
                     'Library/bin/taskboard', 'Library/taskboard-zh-hk.json')

def scan_text(path, text, denied=()):
    findings = []
    relative = Path(path)
    if relative.parts and relative.parts[0] in PRIVATE_ROOTS:
        findings.append({'path': path, 'rule': 'private-project-root'})
    if relative.name in PRIVATE_FILES or relative.suffix.lower() in ('.pem', '.key', '.p12', '.pfx'):
        findings.append({'path': path, 'rule': 'credential-file'})
    for name, pattern in RULES.items():
        for match in pattern.finditer(text):
            findings.append({'path': path, 'line': text.count('\n', 0, match.start()) + 1, 'rule': name})
    for value in denied:
        if value.lower() in text.lower() or value.lower() in path.lower():
            findings.append({'path': path, 'rule': 'private-identifier'})
    return findings

def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
                          capture_output=True).stdout

def scan_current_text(path, text, denied=()):
    """Reuse generic privacy rules without loading any personal configuration."""
    findings = scan_text(path, text, denied)
    for number, line in enumerate((path + '\n' + text).splitlines()):
        for kind in PRIVACY.hits(line, (), ''):
            findings.append({'path': path, 'line': number, 'rule': 'personal-value', 'kind': kind})
    return findings

def scan_history(root, denied=()):
    findings = []
    objects = git(root, 'rev-list', '--objects', '--all').decode().splitlines()
    objects += git(root, 'for-each-ref', '--format=%(objectname)').decode().splitlines()
    seen = set()
    for row in objects:
        fields = row.split(' ', 1)
        oid = fields[0]
        if oid in seen:
            continue
        seen.add(oid)
        kind = git(root, 'cat-file', '-t', oid).strip()
        if kind not in (b'blob', b'commit', b'tag'):
            continue
        path = fields[1] if len(fields) == 2 else 'git/' + kind.decode()
        data = git(root, 'cat-file', '-p', oid)
        for finding in scan_text(path, data.decode('utf-8', errors='replace'), denied):
            findings.append(dict(finding, object=oid))
    return findings

def scan_tree(root, denied=()):
    findings = []
    for entry in git(root, 'ls-files', '-s', '-z').split(b'\0'):
        if not entry:
            continue
        meta, raw_path = entry.split(b'\t', 1)
        mode, oid, stage = meta.decode().split()
        path = raw_path.decode()
        if any(path == local_path or path.startswith(local_path.rstrip('/') + '/')
               for local_path in PRIVATE_RUNTIME):
            findings.append({'path': path, 'rule': 'private-runtime-state'})
        if any(path == private_path or path.startswith(private_path.rstrip('/') + '/')
               for private_path in PRIVATE_DASHBOARD):
            findings.append({'path': path, 'rule': 'private-dashboard'})
        if mode == '160000':
            findings.append({'path': path, 'rule': 'nested-repository'})
            continue
        if mode == '120000':
            link = git(root, 'cat-file', 'blob', oid).decode().strip()
            findings.extend(scan_current_text(path, link, denied))
            try:
                (root / path).parent.joinpath(link).resolve().relative_to(root.resolve())
            except ValueError:
                findings.append({'path': path, 'rule': 'escaping-symlink'})
            continue
        data = git(root, 'cat-file', 'blob', oid)
        if b'\0' in data:
            findings.append({'path': path, 'rule': 'unreviewed-binary'})
        findings.extend(scan_current_text(path, data.decode('utf-8', errors='replace'), denied))
        working = root / path
        try:
            working.resolve().relative_to(root.resolve())
        except ValueError:
            findings.append({'path': path, 'rule': 'escaping-working-path'})
            continue
        if working.is_file() and not working.is_symlink():
            working_data = working.read_bytes()
            if working_data != data:
                findings.extend(scan_current_text(path, working_data.decode('utf-8', errors='replace'), denied))
    return findings

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--deny', action='append', default=[], help='additional private identifier; never pass credentials')
    args = parser.parse_args()
    findings = scan_tree(ROOT, args.deny)
    if args.history:
        findings.extend(scan_history(ROOT, args.deny))
    print(json.dumps({'schema': 1, 'findings': findings, 'passed': not findings}, indent=2))
    return int(bool(findings))

if __name__ == '__main__':
    raise SystemExit(main())
