#!/usr/bin/env python3
"""Grade the frozen twenty real-work library queries, with errors separate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library import search


def evaluate(index, cases):
    rows, errors = [], []
    if not isinstance(cases, list):
        return {'passed': 0, 'total': 0, 'errors': ['cases must be a list'],
                'cases': [], 'accepted': False}
    if isinstance(index, dict) and index.get('diagnostics'):
        errors.append('source index is incomplete; resolve its diagnostics')
    if len(cases) != 20:
        errors.append('exactly twenty frozen cases are required')
    for number, case in enumerate(cases, 1):
        try:
            hits = search(index, case['query'], case['project'], 'codex', 5)
            ranked = [hit['entry']['id'] for hit in hits]
            rows.append({'query': case['query'], 'expected': case['expected'],
                         'ranked': ranked, 'passed': case['expected'] in ranked})
        except (KeyError, TypeError, ValueError, OSError) as exc:
            errors.append('case %s: %s' % (number, exc))
    passed = sum(row['passed'] for row in rows)
    return {'passed': passed, 'total': len(cases), 'errors': errors, 'cases': rows,
            'accepted': len(cases) == 20 and not errors and passed >= 16}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--cases', type=Path,
                        default=Path(__file__).parent / 'tests/fixtures/library-queries.json')
    args = parser.parse_args(argv)
    try:
        result = evaluate(json.loads(args.index.read_text(encoding='utf-8')),
                          json.loads(args.cases.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 2 if result['errors'] else (0 if result['accepted'] else 1)


if __name__ == '__main__':
    raise SystemExit(main())
