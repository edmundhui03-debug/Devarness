#!/usr/bin/env python3
"""Run the portable harness checks; optional device runtimes have separate tests."""
import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOG_TAIL = 8000
PORTABLE_SUITES = (
    '.claude/hooks/test_guard_git_amend.py',
    '.claude/hooks/test_guard_heredoc.py',
    '.claude/hooks/test_guard_vendor_code.py',
    'Library/tests/test_line_endings.py',
    'Library/tests/test_delegate_refs.py',
    'Library/tests/test_library.py',
    'Library/tests/test_library_eval.py',
    'Library/tests/test_library_pick.py',
    'Library/tests/test_md_status.py',
    'Library/tests/test_i18n.py',
    'Library/tests/test_publish_check.py',
    'Library/tests/test_vercel_find.py',
    'Library/tests/test_video_study.py',
    'Library/tests/test_tieitup.py',
)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core-only', action='store_true')
    args = parser.parse_args()
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    for relative in tracked:
        path = ROOT / relative
        if path.suffix == '.py' and not path.is_symlink():
            ast.parse(path.read_text(encoding='utf-8'), filename=relative, feature_version=(3, 9))
    commands = [[sys.executable, 'tools/bootstrap.py', '--check'],
                [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                [sys.executable, 'tools/release_check.py', '--history']]
    if not args.core_only:
        commands += [[sys.executable, path] for path in PORTABLE_SUITES]
    failures = []
    for command in commands:
        print('\nCHECK ' + ' '.join(command[1:]), flush=True)
        result = subprocess.run(command, cwd=ROOT, timeout=600, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        print(result.stdout[-LOG_TAIL:] + result.stderr[-LOG_TAIL:], flush=True)
        if result.returncode:
            failures.append(' '.join(command[1:]))
    if failures:
        print('\nFAILED: ' + '; '.join(failures))
        return 1
    print('\nPASS: %d portable check commands; optional runtime integrations not claimed.' % len(commands))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
