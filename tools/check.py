#!/usr/bin/env python3
"""Run the portable harness checks; optional device runtimes have separate tests."""
import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LOG_TAIL = 8000
DEFAULT_TIMEOUT = 600
TIEITUP_TIMEOUT = 900
PORTABLE_SUITES = (
    '.claude/hooks/test_guard_git_amend.py',
    '.claude/hooks/test_guard_heredoc.py',
    '.claude/hooks/test_guard_vendor_code.py',
    '.claude/hooks/test_post_edit_check.py',
    'Harness/tests/test_line_endings.py',
    'Harness/tests/test_new_device.py',
    'Harness/tests/test_update_tools.py',
    'Harness/tests/test_delegate_refs.py',
    'Harness/tests/test_library.py',
    'Harness/tests/test_library_eval.py',
    'Harness/tests/test_library_pick.py',
    'Harness/tests/test_md_status.py',
    'Harness/tests/test_i18n.py',
    'Harness/tests/test_publish_check.py',
    'Harness/tests/test_vercel_find.py',
    'Harness/tests/test_video_study.py',
    'Harness/tests/test_tieitup.py',
)

def run_check(command, timeout):
    started = time.perf_counter()
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=timeout, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        outputs = (result.stdout, result.stderr)
        status = 'PASS' if result.returncode == 0 else 'FAIL'
    except subprocess.TimeoutExpired as error:
        outputs = (error.stdout, error.stderr)
        status = 'TIMEOUT'
    except OSError as error:
        outputs = ('', str(error))
        status = 'ERROR'
    for output in outputs:
        if isinstance(output, bytes):
            output = output.decode('utf-8', errors='replace')
        print((output or '')[-LOG_TAIL:], end='', flush=True)
    print('\n%s (%.2fs)' % (status, time.perf_counter() - started), flush=True)
    return status == 'PASS'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--core-only', action='store_true')
    names = ['bootstrap', 'core', 'release'] + [Path(path).stem for path in PORTABLE_SUITES]
    modes.add_argument('--only', nargs='+', choices=names,
                       help='partial rerun of named checks; full acceptance still requires the default run')
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
    if args.only:
        commands = [commands[names.index(name)] for name in dict.fromkeys(args.only)]
    scope = 'PARTIAL ' if args.core_only or args.only else ''
    if scope:
        print('PARTIAL verification; run without selection flags for full acceptance.', flush=True)
    failures = []
    for command in commands:
        print('\nCHECK ' + ' '.join(command[1:]), flush=True)
        # A Windows full-suite run took 600.7s;
        # its per-call deadlines and performance assertions remain in place.
        timeout = TIEITUP_TIMEOUT if command[-1] == 'Harness/tests/test_tieitup.py' else DEFAULT_TIMEOUT
        if not run_check(command, timeout):
            failures.append(' '.join(command[1:]))
    if failures:
        print('\n' + scope + 'FAILED: ' + '; '.join(failures))
        return 1
    print('\n%sPASS: %d portable check commands; optional runtime integrations not claimed.' % (scope, len(commands)))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
