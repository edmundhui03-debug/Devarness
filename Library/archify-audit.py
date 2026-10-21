#!/usr/bin/env python3
"""Inventory tracked HTML for Archify adoption; never writes or grades visual polish."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def inventory():
    legacy = {}
    for line in (ROOT / 'Library/i18n-legacy.txt').read_text().splitlines():
        if line and not line.startswith('#'):
            p, digest = line.split('\t')
            legacy[p] = digest
    rows = []
    for name, root in [('dev', ROOT)]:
        files = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--', '*.html'])
        for raw in files.decode().split('\0'):
            if not raw:
                continue
            path = root / raw
            if not path.is_file():
                continue
            content = path.read_text(encoding='utf-8', errors='replace')
            digest = hashlib.sha256(content.encode()).hexdigest()
            title = re.search(r'<title[^>]*>(.*?)</title>', content, re.S | re.I)
            kind = 'active-page'
            if legacy.get(raw) == digest:
                kind = 'preserved-history'
            elif '/_review/' in '/' + raw or '/tests/' in '/' + raw:
                kind = 'evidence-or-fixture'
            elif 'templates/' in raw:
                kind = 'template'
            elif raw.startswith('gateway/') or raw.endswith('/index.html'):
                kind = 'application-entry'
            rows.append({'repository': name, 'path': raw, 'sha256_lf': digest,
                         'title': re.sub(r'\s+', ' ', title.group(1)).strip() if title else '',
                         'kind': kind, 'review': 'static-inventory-only',
                         'diagram_candidate': bool(re.search(r'<svg|mermaid|flowchart|architecture', content, re.I)),
                         'utf8_in_first_1024': bool(re.search(r'charset\s*=\s*[\"\']?utf-8', content[:1024], re.I)),
                         'viewport': bool(re.search(r'name\s*=\s*[\"\']viewport', content, re.I)),
                         'bilingual_toggle': 'page-lang-zh' in content})
    return {'schema': 1, 'date': '2026-10-08', 'scope': 'tracked HTML in dev',
            'meaning': 'Static inventory is not visual or semantic acceptance.', 'pages': rows}


if __name__ == '__main__':
    print(json.dumps(inventory(), ensure_ascii=False, indent=2))
