"""tieitup must flag only changed lines, never block, and learn from its own record."""
import datetime
from importlib.machinery import SourceFileLoader
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / 'Library/bin/tieitup'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LINE = re.compile(r'^(?P<path>[^:]+):(?P<line>\d+) \[(?P<check>[a-z0-9-]+) (?P<id>[0-9a-f]{8})\] .+ \(.+\)$')


def load():
    loader = SourceFileLoader('tieitup_under_test', str(TOOL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


M = load() if TOOL.is_file() else None


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)
    return path


def git(cwd, *args):
    done = subprocess.run(['git', '-C', str(cwd)] + list(args), capture_output=True, text=True,
                          encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL,
                          creationflags=NO_WINDOW, timeout=30)
    if done.returncode:
        raise RuntimeError('git %s: %s' % (' '.join(args), done.stderr))
    return done.stdout


class Repo:
    """A throwaway git repository with one commit, so HEAD exists."""

    def __init__(self, base):
        self.path = Path(base) / 'repo'
        self.path.mkdir()
        git(self.path, 'init', '-q')
        git(self.path, 'config', 'user.email', 'test@example.invalid')
        git(self.path, 'config', 'user.name', 'Test')
        git(self.path, 'config', 'core.autocrlf', 'false')
        self.commit({'README.txt': 'fixture\n'})

    def write(self, name, text):
        return write(self.path / name, text)

    def commit(self, files):
        for name, text in files.items():
            self.write(name, text)
        git(self.path, 'add', '--', *files)
        git(self.path, 'commit', '-q', '-m', 'fixture')


def ponytail_root(base):
    """A dev root holding only a Ponytail clone with one skill."""
    root = Path(base) / 'root'
    clone = root / 'Library/ponytail'
    clone.mkdir(parents=True)
    git(clone, 'init', '-q')
    git(clone, 'config', 'user.email', 'test@example.invalid')
    git(clone, 'config', 'user.name', 'Test')
    git(clone, 'config', 'core.autocrlf', 'false')
    commit_ponytail(root, {'skills/ponytail/SKILL.md': 'rules\n'})
    return root


def commit_ponytail(root, files):
    clone = Path(root) / 'Library/ponytail'
    for name, text in files.items():
        write(clone / name, text)
    git(clone, 'add', '--', *files)
    git(clone, 'commit', '-q', '-m', 'move')


def bench_evidence(root, claude='2.1.292 (Claude Code)', model='claude-opus-5-5', date='2026-10-15'):
    base = {'ponytail_commit': 'a' * 40, 'claude': claude, 'model': model}
    summary = {'date': date, 'headline': 'measured', 'fingerprint': {'ponytail': base, 'ponytail2': base}}
    return write(Path(root) / ('PRDs and Specs/004 TieItUp/evidence/bench-%s.json' % date), json.dumps(summary))


class Base(unittest.TestCase):
    def setUp(self):
        if M is None:
            self.fail('Library/bin/tieitup does not exist yet')
        self.tmp = str(Path(tempfile.mkdtemp(prefix='tieitup-test-')).resolve())
        self.home = Path(self.tmp) / 'home'
        self.old_home = os.environ.get('TIEITUP_HOME')
        os.environ['TIEITUP_HOME'] = str(self.home)
        self.repo = Repo(self.tmp)

    def tearDown(self):
        if self.old_home is None:
            os.environ.pop('TIEITUP_HOME', None)
        else:
            os.environ['TIEITUP_HOME'] = self.old_home
        shutil.rmtree(self.tmp, ignore_errors=True)

    def main(self, *argv, cwd=None):
        out, err = io.StringIO(), io.StringIO()
        code = M.main(list(argv), cwd=str(cwd or self.repo.path), out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def findings(self, name, text):
        """Check one untracked file by name: every line counts as new."""
        self.repo.write(name, text)
        code, out, err = self.main('check', '--', name)
        self.assertEqual(code, 0, err)
        found = []
        for line in out.splitlines():
            match = LINE.match(line)
            self.assertTrue(match, 'not a finding line: %r' % line)
            self.assertEqual(match.group('path'), name)
            found.append((int(match.group('line')), match.group('check')))
        return found

    def checks(self, name, text):
        return {check for _, check in self.findings(name, text)}

    def fires(self, check, name, text, line=None):
        found = self.findings(name, text)
        hits = [at for at, which in found if which == check]
        self.assertTrue(hits, '%s did not fire on %s: %r' % (check, name, found))
        if line is not None:
            self.assertIn(line, hits)

    def silent(self, check, name, text):
        found = self.findings(name, text)
        self.assertNotIn(check, {which for _, which in found}, found)

    def cli(self, *argv, cwd=None):
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        done = subprocess.run([sys.executable, str(TOOL)] + list(argv), cwd=str(cwd or self.repo.path),
                              capture_output=True, text=True, encoding='utf-8', errors='replace',
                              stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, env=env, timeout=60)
        return done.returncode, done.stdout, done.stderr


class ChecksFireAndStaySilent(Base):
    def test_bare_except(self):
        self.fires('bare-except', 'a.py', 'try:\n    go()\nexcept:\n    raise\n', 3)
        self.silent('bare-except', 'b.py', 'try:\n    go()\nexcept ValueError:\n    raise\n')

    def test_swallowed_error_python(self):
        self.fires('swallowed-error', 'a.py', 'try:\n    go()\nexcept OSError:\n    pass\n', 3)
        self.fires('swallowed-error', 'c.py', 'try:\n    go()\nexcept OSError:\n    ...\n')
        self.silent('swallowed-error', 'b.py',
                    'try:\n    go()\nexcept OSError:\n    pass  # the file may not exist yet\n')

    def test_swallowed_error_bash_and_js(self):
        self.fires('swallowed-error', 'a.sh', 'rm -f x || true\n', 1)
        self.fires('swallowed-error', 'c.sh', 'rm -f x || :\n', 1)
        self.silent('swallowed-error', 'b.sh', 'rm -f x || true  # absent is fine\n')
        self.fires('swallowed-error', 'a.js', 'try { go(); } catch (e) {}\n', 1)
        self.fires('swallowed-error', 'c.ts', 'try {\n  go();\n} catch {\n}\n')
        self.silent('swallowed-error', 'b.js', 'try { go(); } catch (e) { /* absent is fine */ }\n')

    def test_unchecked_run(self):
        self.fires('unchecked-run', 'a.py', "import subprocess\nsubprocess.run(['ls'])\n", 2)
        self.fires('unchecked-run', 'c.py', "import os\nos.system('ls')\n", 2)
        self.silent('unchecked-run', 'b.py', "import subprocess\ndone = subprocess.run(['ls'])\n"
                    "print(done.returncode)\nsubprocess.run(['ls'], check=True)\n"
                    "subprocess.call(['kill', '1'])  # best effort: it may be gone\n")

    def test_open_file(self):
        self.fires('open-file', 'a.py', "f = open('x')\nprint(f.read())\nf.close()\n", 1)
        self.fires('open-file', 'c.py', "with open('x', 'w') as fh:\n    fh.write('a')\n", 1)
        self.silent('open-file', 'b.py', "with open('x', 'w', encoding='utf-8', newline='\\n') as fh:\n"
                    "    fh.write('a')\nraw = open('x', 'rb')\n"
                    "def get():\n    fh = open('x')\n    return fh\n"
                    "class K:\n    def __init__(self):\n        self.fh = open('x')\n")

    def test_py39(self):
        self.fires('py39', 'a.py', "from pathlib import Path\nPath('x').write_text('a', encoding='utf-8', newline='\\n')\n", 2)
        self.silent('py39', 'b.py', "from pathlib import Path\nPath('x').write_text('a', encoding='utf-8')\n")

    def test_shell_true(self):
        self.fires('shell-true', 'a.py', "import subprocess\nsubprocess.run('ls', shell=True, check=True)\n", 2)
        self.silent('shell-true', 'b.py', "import subprocess\nsubprocess.run(['ls'], check=True)\n")

    def test_vague_name(self):
        self.fires('vague-name', 'a.py', 'foo = 1\n', 1)
        self.fires('vague-name', 'c.py', 'data2 = 1\n', 1)
        self.fires('vague-name', 'd.py', 'customer = 1\ncustomer_info = 2\n', 2)
        self.fires('vague-name', 'e.js', 'const stuff = 1;\n', 1)
        self.fires('vague-name', 'f.sh', 'list2=1\n', 1)
        self.silent('vague-name', 'b.py', 'data = load()\ninfo = 1\nhandle = 2\ntmp = 3\ntemp = 4\n'
                    'for foo in items:\n    print(foo)\nnames = [bar for bar in items]\n')

    def test_nesting_python(self):
        deep = ('def f(a):\n    if a:\n        for b in a:\n            while b:\n'
                '                try:\n                    if b:\n                        go()\n'
                '                except OSError:\n                    raise\n')
        self.fires('nesting', 'a.py', deep, 6)
        self.assertEqual([c for _, c in self.findings('a2.py', deep)].count('nesting'), 1)
        flat = ('def f(a):\n    if a:\n        for b in a:\n            while b:\n'
                '                with open(b) as fh:\n                    if b:\n                        go()\n'
                '                    elif a:\n                        stop()\n')
        self.silent('nesting', 'b.py', flat)

    def test_nesting_bash_and_braces(self):
        deep_sh = ('if a; then\n for x in y; do\n  while b; do\n   until c; do\n'
                   '    case $x in\n     *) echo hi ;;\n    esac\n   done\n  done\n done\nfi\n')
        self.fires('nesting', 'a.sh', deep_sh, 5)
        self.silent('nesting', 'b.sh', 'if a; then\n for x in y; do\n  while b; do\n   echo hi\n  done\n done\nfi\n')
        deep_js = ('function f(a) {\n  if (a) {\n    for (;;) {\n      while (a) {\n'
                   '        try {\n          if (a) {\n            go();\n          }\n'
                   '        } catch (e) { throw e; }\n      }\n    }\n  }\n}\n')
        self.fires('nesting', 'a.js', deep_js, 6)
        flat_c = ('int f(int a) {\n  if (a) {\n    go();\n  } else if (b) {\n    stop();\n  } else {\n'
                  '    for (;;) {\n      while (a) {\n        switch (a) {\n        case 1: break;\n        }\n'
                  '      }\n    }\n  }\n  return 0;\n}\n')
        self.silent('nesting', 'b.c', flat_c)

    def test_magic_number(self):
        self.fires('magic-number', 'a.py', 'a = wait(86400)\nb = wait(86400)\n', 1)
        self.silent('magic-number', 'b.py', 'DAY = 86400\na = wait(DAY)\nb = wait(DAY)\nc = f(2)\nd = f(2)\n'
                    'def g(x=500):\n    return x\ne = h(500)\n')
        self.silent('magic-number', 'tests/test_b.py', 'a = wait(86400)\nb = wait(86400)\n')
        self.silent('magic-number', 'c.c', '#define DAY 86400\nint a = DAY;\n')

    def test_magic_number_preserves_explicit_binary_megabyte_factors(self):
        self.silent('magic-number', 'caps.py',
                    'retain(a, 1024 * 1024)\nretain(b, 1024 * 1024)\n')
        self.fires('magic-number', 'bare.py', 'retain(a, 1024)\nretain(b, 1024)\n', 1)
        self.fires('magic-number', 'sum.py', 'a = 1024 + 1024\n', 1)
        self.fires('magic-number', 'other.py', 'a = 1024 * 512\nb = 1024 * 512\n', 1)

    def test_commented_code(self):
        self.fires('commented-code', 'a.py', 'x = 1\n# y = compute(x)\n', 2)
        self.fires('commented-code', 'c.py', 'x = 1  # written by Edmund\n', 1)
        self.fires('commented-code', 'd.js', 'let x = 1;\n// go(x);\n', 2)
        self.fires('commented-code', 'e.sh', 'x=1\n# y=2\n', 2)
        self.fires('commented-code', 'f.c', '/* @author someone */\nint x;\n', 1)
        self.silent('commented-code', 'b.py', '#!/usr/bin/env python3\n# compute the total before sorting\n'
                    'x = 1  # done\n# Note: slow\n')
        self.silent('commented-code', 'b.sh', '# all done here\nx=1\n# MSYS_NO_PATHCONV=1 set; elsewhere it fails\n')
        self.fires('commented-code', 'g.sh', 'x=1\n# NAME="a b"; export NAME\n', 2)
        self.silent('commented-code', 'c.py', 'x = 1  # "restored only from a dated snapshot"\n')
        self.silent('commented-code', 'c.sh', "python3 - <<'EOF'\n# newline='x' here is Python\nx = 1\nEOF\n"
                    'cat <<-END\n\t# y=2 is text\n\tEND\n')
        self.fires('commented-code', 'd.sh', "cat <<'EOF'\ntext\nEOF\n# y=2\n", 4)

    def test_duplicate(self):
        block = ''.join('v%d = load(%d)\n' % (i, i) for i in range(6))
        self.fires('duplicate', 'a.py', block + 'print(1)\n' + block, 8)
        long = ''.join('u%d = load(%d)\n' % (i, i) for i in range(14))
        found = self.findings('long.py', long + 'print(1)\n' + long)
        self.assertEqual([at for at, check in found if check == 'duplicate'], [1, 16], 'one finding per copy')
        self.silent('duplicate', 'b.py', ''.join('v%d = load(%d)\n' % (i, i) for i in range(12)))
        self.silent('duplicate', 'tests/test_a.py', block + 'print(1)\n' + block)

    def test_duplicate_keeps_constant_container_string_contents(self):
        distinct = ''.join('    %r,\n' % ('gateway/source_%d.py' % i) for i in range(12))
        self.silent('duplicate', 'manifest.py', 'ADAPTERS = (\n' + distinct + ')\n')
        repeated = ''.join('    %r,\n' % ('gateway/source_%d.py' % i) for i in range(6))
        self.fires('duplicate', 'copies.py', 'ADAPTERS = (\n' + repeated + repeated + ')\n', 8)
        spaced = ''.join('    %r,\n' % ('gateway /source_%d.py' % i) for i in range(6))
        self.silent('duplicate', 'spaces.py', 'ADAPTERS = (\n' + repeated + spaced + ')\n')

    def test_shortcut(self):
        self.fires('shortcut', 'a.py', 'x = 1  # TODO make it faster\n', 1)
        self.fires('shortcut', 'c.py', 'x = 1  # shortcut: one user only\n', 1)
        self.fires('shortcut', 'd.js', 'let x = 1; // FIXME\n', 1)
        self.silent('shortcut', 'b.py', "x = 1  # shortcut: one user only, upgrade when a second appears\n"
                    "y = 'TODO in a string'\n# todo in lower case is prose\n")

    def test_new_dependency(self):
        self.fires('new-dependency', 'a.py', 'import notarealmodule_tieitup\n', 1)
        self.fires('new-dependency', 'c.py', 'from notarealmodule_tieitup.sub import x\n', 1)
        self.repo.commit({'helper.py': 'X = 1\n', 'other.py': 'import yaml_tieitup_fake\n'})
        self.silent('new-dependency', 'b.py', 'import json\nimport os.path\nimport helper\n'
                    'import yaml_tieitup_fake\nfrom . import sibling\n')

    def test_new_dependency_manifests(self):
        self.repo.commit({'requirements.txt': 'flask==1.0\n',
                          'package.json': '{\n  "dependencies": {\n    "left-pad": "1.0.0"\n  }\n}\n'})
        self.repo.write('requirements.txt', 'flask==2.0\nrequests==2.0\n')
        self.repo.write('package.json', '{\n  "name": "x",\n  "dependencies": {\n    "left-pad": "1.0.0",\n'
                        '    "lodash": "4.0.0"\n  }\n}\n')
        code, out, _ = self.main('check')
        hits = [m.group('path') + ':' + m.group('line') for m in map(LINE.match, out.splitlines())
                if m and m.group('check') == 'new-dependency']
        self.assertEqual(sorted(hits), ['package.json:5', 'requirements.txt:2'], out)

    def test_one_implementation(self):
        base = ('from abc import ABC, abstractmethod\n\n\nclass Store(ABC):\n'
                '    @abstractmethod\n    def save(self):\n        raise NotImplementedError\n\n\n'
                'class FileStore(Store):\n    def save(self):\n        return 1\n')
        self.fires('one-implementation', 'a.py', base, 4)
        self.silent('one-implementation', 'b.py', base.replace('Store', 'Sink') +
                    '\n\nclass NetSink(Sink):\n    def save(self):\n        return 2\n')
        self.silent('one-implementation', 'c.py', 'from typing import Protocol\n\n\nclass Saver(Protocol):\n'
                    '    def save(self): ...\n')
        self.fires('one-implementation', 'd.ts', 'interface Shape { area(): number }\n'
                   'class Square implements Shape { area() { return 1; } }\n', 1)
        self.silent('one-implementation', 'e.ts', 'interface Point { x: number }\n')

    def test_pass_through(self):
        self.fires('pass-through', 'a.py', 'def load(path, mode):\n    """Load it."""\n    return read(path, mode)\n', 1)
        self.silent('pass-through', 'b.py', 'import functools\n\n'
                    '@functools.lru_cache()\ndef load(path):\n'
                    '    return read(path)\n\ndef swap(a, b):\n    return read(b, a)\n\n'
                    'class K:\n    def load(self, path):\n        return read(path)\n')
        self.silent('pass-through', 'tests/test_c.py', 'def load(path):\n    return read(path)\n')


class WholeChange(Base):
    def test_untested_logic_fires_on_a_new_untested_file(self):
        self.repo.write('lib.py', 'def pick(xs):\n    for x in xs:\n        if x:\n            return x\n')
        git(self.repo.path, 'add', 'lib.py')
        code, out, _ = self.main('check')
        self.assertIn('untested-logic', out)
        self.assertEqual(out.count('untested-logic'), 1)

    def test_untested_logic_silent_with_a_test_or_assert(self):
        self.repo.write('lib.py', 'def pick(xs):\n    for x in xs:\n        if x:\n            return x\n')
        self.repo.write('tests/test_lib.py', 'from lib import pick\nassert pick([1]) == 1\n')
        git(self.repo.path, 'add', 'lib.py', 'tests/test_lib.py')
        code, out, _ = self.main('check')
        self.assertNotIn('untested-logic', out)

    def test_untested_logic_silent_on_a_branch_inside_an_existing_function(self):
        self.repo.commit({'lib.py': 'def pick(xs):\n    return xs[0]\n'})
        self.repo.write('lib.py', 'def pick(xs):\n    if not xs:\n        return None\n    return xs[0]\n')
        code, out, _ = self.main('check')
        self.assertNotIn('untested-logic', out)

    def test_untested_logic_silent_on_named_paths(self):
        self.repo.write('lib.py', 'def pick(xs):\n    for x in xs:\n        return x\n')
        git(self.repo.path, 'add', 'lib.py')
        code, out, _ = self.main('check', '--', 'lib.py')
        self.assertNotIn('untested-logic', out)

    def test_duplicate_across_added_files(self):
        block = ''.join('w%d = fetch(%d)\n' % (i, i) for i in range(6))
        self.repo.write('one.py', block)
        self.repo.write('two.py', 'start()\n' + block)
        git(self.repo.path, 'add', 'one.py', 'two.py')
        code, out, _ = self.main('check')
        self.assertIn('[duplicate', out)

    def test_old_violation_is_not_reported_but_audit_finds_it(self):
        self.repo.commit({'old.py': 'try:\n    go()\nexcept:\n    raise\n'})
        self.repo.write('old.py', 'try:\n    go()\nexcept:\n    raise\nvalue = 1\n')
        code, out, _ = self.main('check', '--', 'old.py')
        self.assertEqual(out, '')
        code, out, _ = self.main('check')
        self.assertNotIn('[', out.split('tieitup:')[0])
        code, out, _ = self.main('audit', 'old.py')
        self.assertIn('old.py:3 [bare-except', out)

    def test_staged_and_ranges(self):
        self.repo.commit({'r.py': 'x = 1\n'})
        self.repo.commit({'r.py': 'x = 1\ntry:\n    go()\nexcept:\n    raise\n'})
        code, out, _ = self.main('check', 'HEAD^!')
        self.assertIn('r.py:4 [bare-except', out)
        code, out, _ = self.main('check', 'HEAD~1..HEAD')
        self.assertIn('r.py:4 [bare-except', out)
        self.repo.write('r.py', 'x = 1\ntry:\n    go()\nexcept:\n    raise\nfoo = 2\n')
        code, out, _ = self.main('check', '--staged')
        self.assertNotIn('vague-name', out)
        git(self.repo.path, 'add', 'r.py')
        code, out, _ = self.main('check', '--staged')
        self.assertIn('r.py:6 [vague-name', out)

    def test_balance_line(self):
        self.repo.commit({'b.py': 'x = 1\n'})
        self.repo.write('b.py', 'x = 2\nfoo = 3\n')
        code, out, _ = self.main('check')
        last = out.strip().splitlines()[-1]
        self.assertRegex(last, r'^tieitup: \+2 -1 lines in 1 file; 1 finding')

    def test_callers_aid(self):
        self.repo.commit({'lib.py': 'def helper(x):\n    return x + 1\n',
                          'main.py': 'from lib import helper\nprint(helper(1))\n',
                          'run.sh': 'greet() {\n  echo hi\n}\n', 'use.sh': '. ./run.sh\ngreet\n'})
        self.repo.write('lib.py', 'def helper(x):\n    return x + 2\n')
        self.repo.write('run.sh', 'greet() {\n  echo hello\n}\n')
        code, out, _ = self.main('check')
        self.assertIn('callers of helper', out)
        self.assertIn('main.py:2', out)
        self.assertIn('callers of greet', out)
        self.assertIn('use.sh:2', out)
        code, out, _ = self.main('check', '--', 'lib.py')
        self.assertNotIn('callers', out)


class Reading(Base):
    def test_unknown_type_is_skipped(self):
        self.assertEqual(self.findings('notes.txt', 'try:\nexcept:\n    pass\nfoo = 1\n'), [])

    def test_extensionless_python_shebang_is_checked(self):
        self.assertIn('bare-except', self.checks('tool', '#!/usr/bin/env python3\ntry:\n    go()\nexcept:\n    raise\n'))
        self.assertIn('swallowed-error', self.checks('tool2', '#!/bin/sh\nrm x || true\n'))
        self.assertIn('swallowed-error', self.checks('tool3', '#!/usr/bin/env bash\nrm x || true\n'))

    def test_untracked_named_file_is_all_new(self):
        found = self.findings('fresh.py', 'x = 1\ntry:\n    go()\nexcept:\n    raise\n')
        self.assertIn((4, 'bare-except'), found)

    def test_outside_any_repository(self):
        outside = Path(self.tmp) / 'loose'
        write(outside / 'x.py', 'try:\n    go()\nexcept:\n    raise\n')
        env = os.environ.get('GIT_CEILING_DIRECTORIES')
        os.environ['GIT_CEILING_DIRECTORIES'] = str(Path(self.tmp))
        try:
            code, out, err = self.main('check', '--', 'x.py', cwd=outside)
        finally:
            if env is None:
                os.environ.pop('GIT_CEILING_DIRECTORIES', None)
            else:
                os.environ['GIT_CEILING_DIRECTORIES'] = env
        self.assertEqual(code, 0)
        self.assertIn('x.py:3 [bare-except', out)

    def test_id_survives_lines_inserted_above(self):
        text = 'try:\n    go()\nexcept:\n    raise\n'
        first = self.main('check', '--', self.repo.write('m.py', text).name)[1]
        second = self.main('check', '--', self.repo.write('m.py', 'a = 1\nb = 2\n' + text).name)[1]
        id1 = LINE.match(first.splitlines()[0]).group('id')
        match = LINE.match(second.splitlines()[0])
        self.assertEqual(match.group('id'), id1)
        self.assertEqual(match.group('line'), '5')

    def test_finding_id_shape(self):
        import hashlib
        expected = hashlib.sha1('\n'.join(['bare-except', 'm.py', 'except:']).encode('utf-8')).hexdigest()[:8]
        self.assertEqual(M.finding_id('bare-except', 'm.py', '  except :  '), expected)

    def test_named_run_prints_only_findings(self):
        self.repo.write('n.py', 'foo = 1\n')
        code, out, err = self.cli('check', '--', 'n.py')
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(line.startswith('n.py:'), line)
            self.assertRegex(line, LINE)
        self.assertIn('(rule 9;', out)

    def test_clean_named_file_prints_nothing(self):
        self.repo.write('ok.py', 'total = sum([1, 2])\n')
        self.assertEqual(self.cli('check', '--', 'ok.py')[1], '')

    def test_exit_codes(self):
        self.assertEqual(self.cli('nonsense')[0], 2)
        self.assertEqual(self.cli('check', '--bogus')[0], 2)
        code, out, err = self.cli('check', 'nosuchref..alsonot')
        self.assertEqual(code, 0)
        self.assertTrue(err.startswith('tieitup: '), err)
        code, out, err = self.cli('check', '--', 'missing.py')
        self.assertEqual(code, 0)
        self.assertIn('tieitup: ', err)

    def test_no_repository_and_no_file_is_a_fault(self):
        outside = Path(self.tmp) / 'empty'
        outside.mkdir()
        env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(Path(self.tmp)))
        done = subprocess.run([sys.executable, str(TOOL), 'check'], cwd=str(outside), capture_output=True,
                              text=True, encoding='utf-8', errors='replace', stdin=subprocess.DEVNULL,
                              creationflags=NO_WINDOW, env=env, timeout=60)
        self.assertEqual(done.returncode, 0)
        self.assertTrue(done.stderr.startswith('tieitup: '), done.stderr)
        self.assertEqual(done.stdout, '')

    def test_large_file_is_fast(self):
        import time
        body = ''.join('def f%d(a):\n    if a:\n        return a + %d\n    return None\n\n' % (i, i)
                       for i in range(200))
        self.repo.write('big.py', body)
        start = time.time()
        code, out, err = self.cli('check', '--', 'big.py')
        self.assertEqual(code, 0, err)
        self.assertLess(time.time() - start, 5.0)


class OtherCommands(Base):
    def test_audit_groups_by_check_and_caps_each_group(self):
        body = ''.join('try:\n    go%d()\nexcept:\n    raise\n' % i for i in range(25))
        self.repo.commit({'pkg/many.py': body, 'pkg/fine.py': 'total = 1\n'})
        code, out, _ = self.main('audit', 'pkg')
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertIn('bare-except: 25 findings', lines)
        self.assertEqual(sum(1 for line in lines if '[bare-except ' in line), 20)
        self.assertIn('  and 5 more', lines)
        self.assertRegex(lines[-1], r'^tieitup audit: \d+ findings in 2 files$')
        self.assertFalse((self.home / 'log.jsonl').exists(), 'an audit must not be recorded')

    def test_audit_finds_untested_functions(self):
        self.repo.commit({'lib.py': 'def pick(xs):\n    if xs:\n        return xs[0]\n\n'
                                    'def kept(xs):\n    if xs:\n        return 1\n',
                          'tests/test_lib.py': 'from lib import kept\nassert kept([1])\n'})
        code, out, _ = self.main('audit')
        self.assertIn("lib.py:1 [untested-logic", out)
        self.assertNotIn("lib.py:5 [untested-logic", out)

    def test_debt_lists_markers_with_age_and_notes_apart(self):
        self.repo.commit({'d.py': 'a = 1  # shortcut: one user only, upgrade when a second appears\n'
                                  'b = 2  # shortcut: no trigger named\n'
                                  'c = 3  # TODO tidy this\n'})
        self.repo.write('e.sh', 'x=1  # ponytail: linear scan; replace above 1000 rows\n')
        code, out, _ = self.main('debt')
        self.assertEqual(code, 0)
        self.assertIn('d.py:1, ceiling: one user only. upgrade: upgrade when a second appears. age: 0 days.', out)
        self.assertIn('d.py:2, ceiling: no trigger named. no-trigger. age: 0 days.', out)
        self.assertIn('e.sh:1, ceiling: linear scan. upgrade: replace above 1000 rows. age: uncommitted.', out)
        notes = out.split('unmarked notes:')[1]
        self.assertIn('d.py:3', notes)
        self.assertNotIn('d.py:1', notes)
        self.assertIn('tieitup debt: 3 markers, 1 with no trigger; 1 unmarked note', out)

    def test_debt_on_a_clean_tree(self):
        code, out, _ = self.main('debt')
        self.assertIn('no shortcut markers', out)

    def test_gain_before_and_after_a_measurement(self):
        root = Path(self.tmp) / 'root'
        lines = M.gain_lines(root)
        self.assertIn('not measured yet', lines[0])
        self.assertIn('Library/ponytail/benchmarks/results/', '\n'.join(lines))
        evidence = root / 'PRDs and Specs/004 TieItUp/evidence'
        write(evidence / 'bench-2026-10-01.json', json.dumps({'headline': 'old', 'date': '2026-10-01', 'fingerprint': 'a'}))
        write(evidence / 'bench-2026-10-20.json', json.dumps({'headline': 'within noise on lines of code',
                                                             'date': '2026-10-20', 'fingerprint': 'f00d'}))
        text = '\n'.join(M.gain_lines(root))
        self.assertIn('within noise on lines of code', text)
        self.assertIn('2026-10-20', text)
        self.assertIn('f00d', text)
        self.assertNotIn('old', text.split('\n')[0])
        self.assertEqual(self.main('gain')[0], 0)

    def test_help_names_levels_commands_stop_and_record(self):
        code, out, _ = self.main('help')
        self.assertEqual(code, 0)
        for word in ('lite', 'full', 'ultra', 'stop tieitup', 'check', 'audit', 'debt', 'gain',
                     'mark', 'miss', 'learn', str(self.home)):
            self.assertIn(word, out)


def jsonl(path):
    with open(str(path), encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


class Record(Base):
    def run_record(self, runs=(), marks=(), misses=()):
        for name, rows in (('log.jsonl', runs), ('marks.jsonl', marks), ('misses.jsonl', misses)):
            write(self.home / name, ''.join(json.dumps(row) + '\n' for row in rows))

    def a_run(self, findings=(), checks=None, path='p.py', base='b' * 40, langs=('python',)):
        revs = M.revisions()
        names = checks or [name for name, langs_, _ in M.CHECKS if set(langs_) & set(langs)]
        counts = {name: sum(1 for f in findings if f[1] == name) for name in names}
        return {'v': 1, 'time': '2026-10-15T00:00:00Z', 'repo': '/r', 'base': base, 'mode': 'worktree',
                'langs': list(langs), 'files': [path],
                'checks': {name: {'rev': revs[name], 'count': counts[name]} for name in names},
                'findings': [{'id': ident, 'check': check, 'path': path, 'line': 1} for ident, check in findings]}

    def proposals(self, root=None):
        return M.proposals(self.home, root or Path(self.tmp) / 'no-root')

    def test_a_run_is_recorded_without_any_code(self):
        flagged = 'foo = compute_marker_text_2026()'
        self.repo.write('r.py', flagged + '\n')
        self.main('check', '--', 'r.py')
        text = (self.home / 'log.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('compute_marker_text_2026', text)
        self.assertNotIn(flagged, text)
        row = jsonl(self.home / 'log.jsonl')[-1]
        for key in ('time', 'repo', 'base', 'mode', 'checks', 'findings', 'files'):
            self.assertIn(key, row)
        self.assertEqual(row['mode'], 'paths')
        self.assertEqual(row['checks']['vague-name']['count'], 1)
        self.assertEqual(set(row['findings'][0]), {'id', 'check', 'path', 'line'})
        self.assertNotIn('untested-logic', row['checks'], 'a run on named paths cannot see the tests')

    def test_the_record_moves_aside_past_its_limit(self):
        write(self.home / 'log.jsonl', 'x' * 200 + '\n')
        old, M.LOG_LIMIT = M.LOG_LIMIT, 100
        try:
            self.repo.write('r.py', 'foo = 1\n')
            self.main('check', '--', 'r.py')
        finally:
            M.LOG_LIMIT = old
        self.assertTrue((self.home / 'log.1.jsonl').is_file())
        self.assertEqual(len(jsonl(self.home / 'log.jsonl')), 1)

    def test_mark_hides_a_false_alarm_and_the_balance_counts_it(self):
        self.repo.commit({'b.py': 'x = 1\n'})
        self.repo.write('b.py', 'x = 1\nfoo = 2\n')
        out = self.main('check')[1]
        ident = LINE.match(out.splitlines()[0]).group('id')
        code, said, _ = self.main('mark', ident, 'fp', 'foo is the protocol word here')
        self.assertEqual(code, 0)
        out = self.main('check')[1]
        self.assertNotIn(ident, out)
        self.assertIn('1 finding, 1 hidden as a false alarm', out)
        self.assertEqual(self.main('check', '--', 'b.py')[1], '')
        mark = jsonl(self.home / 'marks.jsonl')[-1]
        self.assertEqual((mark['id'], mark['verdict'], mark['check']), (ident, 'fp', 'vague-name'))
        self.assertEqual(self.main('mark', ident, 'ok')[0], 0)
        self.assertIn(ident, self.main('check')[1], 'a later ok mark shows it again')

    def test_mark_and_miss_usage_errors_exit_2(self):
        self.assertEqual(self.cli('mark', 'deadbeef', 'fp')[0], 2)
        self.assertEqual(self.cli('mark', 'zz', 'fp')[0], 2)
        self.assertEqual(self.cli('mark', 'deadbeef', 'maybe')[0], 2)
        self.assertEqual(self.cli('miss', 'nowhere', 'what')[0], 2)
        self.assertEqual(self.cli('miss', 'a.py:3', 'what', '--check', 'no-such-check')[0], 2)
        self.assertEqual(self.cli('learn', 'extra')[0], 2)

    def test_miss_is_recorded_and_proposed(self):
        code, _, _ = self.main('miss', 'b.py:3', 'a swallowed error inside a lambda', '--check', 'swallowed-error')
        self.assertEqual(code, 0)
        miss = jsonl(self.home / 'misses.jsonl')[-1]
        self.assertEqual((miss['path'], miss['line'], miss['check']), ('b.py', 3, 'swallowed-error'))
        found = [p for p in self.proposals() if p.startswith('missed')]
        self.assertEqual(len(found), 1)
        self.assertIn('b.py:3', found[0])
        code, out, _ = self.main('learn')
        self.assertIn('missed b.py:3', out)

    def test_four_false_alarms_among_six_give_a_narrow_proposal(self):
        ids = ['%08x' % i for i in range(6)]
        self.run_record([self.a_run([(i, 'magic-number') for i in ids])],
                        [{'id': i, 'verdict': 'fp' if n < 4 else 'ok', 'check': 'magic-number'} for n, i in enumerate(ids)])
        narrow = [p for p in self.proposals() if p.startswith('narrow')]
        self.assertEqual(len(narrow), 1)
        self.assertIn('magic-number', narrow[0])

    def test_three_false_alarms_among_four_give_none(self):
        ids = ['%08x' % i for i in range(4)]
        self.run_record([self.a_run([(i, 'magic-number') for i in ids])],
                        [{'id': i, 'verdict': 'fp' if n < 3 else 'ok', 'check': 'magic-number'} for n, i in enumerate(ids)])
        self.assertFalse([p for p in self.proposals() if p.startswith('narrow')])

    def test_a_fixed_finding_counts_as_decided(self):
        ids = ['%08x' % i for i in range(6)]
        first = self.a_run([(i, 'vague-name') for i in ids])
        second = self.a_run([(i, 'vague-name') for i in ids[:5]])      # the sixth was fixed
        marks = [{'id': i, 'verdict': 'fp', 'check': 'vague-name'} for i in ids[:4]]
        self.run_record([first], marks)
        self.assertFalse([p for p in self.proposals() if p.startswith('narrow')], 'four decided is under five')
        self.run_record([first, second], marks)
        self.assertTrue([p for p in self.proposals() if p.startswith('narrow vague-name')],
                        'the fixed one makes five decided')
        other_base = dict(second, base='c' * 40)
        self.run_record([first, other_base], marks)
        self.assertFalse([p for p in self.proposals() if p.startswith('narrow')], 'fixed needs the same base')

    def test_an_old_revision_does_not_count(self):
        ids = ['%08x' % i for i in range(6)]
        run = self.a_run([(i, 'magic-number') for i in ids])
        run['checks']['magic-number']['rev'] = '00000000'
        self.run_record([run], [{'id': i, 'verdict': 'fp'} for i in ids])
        self.assertFalse([p for p in self.proposals() if p.startswith('narrow')])

    def test_two_hundred_quiet_runs_give_silent_proposals(self):
        self.run_record([self.a_run() for _ in range(200)])
        silent = {p.split()[1].rstrip(':'): p for p in self.proposals() if p.startswith('silent')}
        self.assertIn('vague-name', silent)
        self.assertNotIn('only reported', silent['vague-name'])
        for name in M.NEVER_CUT:
            self.assertIn(name, silent)
            self.assertIn('only reported', silent[name])
        self.run_record([self.a_run() for _ in range(199)])
        self.assertFalse([p for p in self.proposals() if p.startswith('silent')])

    def test_proposals_read_at_most_the_budget(self):
        self.run_record([self.a_run() for _ in range(200)])
        old, M.READ_LIMIT = M.READ_LIMIT, 20000
        try:
            self.assertFalse([p for p in self.proposals() if p.startswith('silent')])
        finally:
            M.READ_LIMIT = old

    def test_unreadable_lines_are_skipped_and_counted(self):
        self.run_record([self.a_run()])
        with open(str(self.home / 'log.jsonl'), 'a', encoding='utf-8', newline='\n') as fh:
            fh.write('{not json\n')
        code, out, _ = self.main('learn')
        self.assertEqual(code, 0)
        self.assertIn('1 unreadable record line skipped', out)

    def test_changed_ponytail_skills_give_drift(self):
        root = ponytail_root(self.tmp)
        with mock.patch.object(M, 'ROOT', root):
            self.main('rechecked')
        self.assertFalse([p for p in self.proposals(root) if p.startswith('drift')])
        commit_ponytail(root, {'skills/ponytail/SKILL.md': 'new rules\n'})
        drift = [p for p in self.proposals(root) if p.startswith('drift')]
        self.assertEqual(len(drift), 1)
        self.assertIn('re-check', drift[0])
        self.assertFalse([p for p in self.proposals() if p.startswith('drift')])

    def test_harness_drift_is_a_proposal_with_the_model_named_rules(self):
        root = ponytail_root(self.tmp)
        bench_evidence(root)
        write(root / 'CLAUDE.md', 'Plain rule.\nOpus 5.5 skips this step, so say it twice.\n')
        with mock.patch.object(M, 'claude_version', lambda: '2.1.292 (Claude Code)'), \
                mock.patch.object(M, 'served_model', lambda root: 'claude-opus-5-6'):
            harness = [p for p in self.proposals(root) if p.startswith('harness')]
        self.assertEqual(len(harness), 1)
        self.assertIn('claude-opus-5-5 -> claude-opus-5-6', harness[0])
        self.assertIn('CLAUDE.md:2', harness[0])
        self.assertIn('prompt-audit', harness[0])

    def test_learn_with_no_record(self):
        with mock.patch.object(M, 'ROOT', Path(self.tmp) / 'no-root'):
            code, out, _ = self.main('learn')
        self.assertEqual(code, 0)
        self.assertIn('no open proposals', out)


class Freshness(Base):
    """TieItUp notices, offline, when Ponytail's skills or the harness move past what it was checked against."""

    def recheck(self, root):
        with mock.patch.object(M, 'ROOT', root):
            return self.main('rechecked')

    def test_rechecked_records_ponytails_commit_and_skills_tree(self):
        root = ponytail_root(self.tmp)
        code, out, _ = self.recheck(root)
        self.assertEqual(code, 0)
        clone = root / 'Library/ponytail'
        record = json.loads((root / M.CHECKED_FILE).read_text(encoding='utf-8'))
        self.assertEqual(record['version'], 1)
        self.assertEqual(record['ponytail_commit'], git(clone, 'rev-parse', 'HEAD').strip())
        self.assertEqual(record['ponytail_skills_tree'], git(clone, 'rev-parse', 'HEAD:skills').strip())
        self.assertIn(record['ponytail_commit'][:7], out)

    def test_a_move_that_leaves_the_skills_alone_needs_no_recheck(self):
        root = ponytail_root(self.tmp)
        self.recheck(root)
        commit_ponytail(root, {'README.md': 'docs\n', 'hooks/x.js': 'x\n'})
        self.assertEqual(M.ponytail_changes(root), [])

    def test_a_skills_change_asks_for_a_recheck(self):
        root = ponytail_root(self.tmp)
        self.recheck(root)
        commit_ponytail(root, {'skills/ponytail-new/SKILL.md': 'more\n'})
        reasons = M.ponytail_changes(root)
        self.assertEqual(len(reasons), 1)
        self.assertIn("Ponytail's skills changed", reasons[0])
        self.assertIn('tieitup rechecked', reasons[0])
        self.recheck(root)
        self.assertEqual(M.ponytail_changes(root), [])

    def test_no_record_or_no_clone_is_said(self):
        root = ponytail_root(self.tmp)
        self.assertEqual(M.ponytail_changes(root), ['no checked record at ' + M.CHECKED_FILE])
        self.recheck(root)
        shutil.rmtree(str(root / 'Library/ponytail'), ignore_errors=True)
        self.assertEqual(M.ponytail_changes(root), ['Ponytail revision unavailable'])

    def test_a_record_of_another_version_is_refused(self):
        root = ponytail_root(self.tmp)
        write(root / M.CHECKED_FILE, json.dumps({'version': 2}))
        self.assertEqual(M.ponytail_changes(root), ['unreadable checked record at ' + M.CHECKED_FILE])

    def test_the_live_record_matches_the_live_clone(self):
        if not (ROOT / 'Library/ponytail/skills').is_dir():
            self.skipTest('no Ponytail clone in this checkout')
        self.assertIsInstance(M.ponytail_changes(ROOT), list)
        self.assertEqual(M.checked(ROOT)['version'], 1)

    def drift(self, root, version='2.1.292 (Claude Code)', model='claude-opus-5-5', today='2026-10-20'):
        return M.harness_changes(root, version=version, model=model,
                                 today=datetime.date(*map(int, today.split('-'))))

    def test_the_same_harness_is_current(self):
        root = ponytail_root(self.tmp)
        bench_evidence(root)
        self.assertEqual(self.drift(root), [])

    def test_a_patch_release_waits_thirty_days(self):
        root = ponytail_root(self.tmp)
        bench_evidence(root)
        self.assertEqual(self.drift(root, version='2.1.300 (Claude Code)'), [])
        reasons = self.drift(root, version='2.1.300 (Claude Code)', today='2026-11-14')
        self.assertEqual(len(reasons), 1)
        self.assertIn('2.1.292 -> 2.1.300', reasons[0])
        self.assertIn('tieitup-bench.py auto', reasons[0])

    def test_a_minor_release_is_due_at_once(self):
        root = ponytail_root(self.tmp)
        bench_evidence(root)
        reasons = self.drift(root, version='2.2.0 (Claude Code)')
        self.assertEqual(len(reasons), 1)
        self.assertIn('2.1.292 -> 2.2.0', reasons[0])

    def test_a_new_model_of_the_same_family_is_due(self):
        root = ponytail_root(self.tmp)
        bench_evidence(root)
        reasons = self.drift(root, model='claude-opus-5-6')
        self.assertEqual(len(reasons), 1)
        self.assertIn('claude-opus-5-5 -> claude-opus-5-6', reasons[0])

    def test_another_family_or_nothing_known_is_not_drift(self):
        root = ponytail_root(self.tmp)
        self.assertEqual(self.drift(root, version='9.0.0 (Claude Code)'), [])   # no benchmark yet
        bench_evidence(root)
        self.assertEqual(self.drift(root, model='claude-sonnet-5-5'), [])
        self.assertEqual(self.drift(root, version=None, model=None), [])

    def test_served_model_is_the_newest_transcripts_last_real_model(self):
        folder = Path(self.tmp) / 'projects'
        old = write(folder / 'old.jsonl', json.dumps({'type': 'assistant', 'message': {'model': 'claude-opus-5-4'}}) + '\n')
        os.utime(str(old), (1, 1))
        write(folder / 'new.jsonl', ''.join(json.dumps(row) + '\n' for row in (
            {'type': 'assistant', 'message': {'model': 'claude-opus-5-5'}},
            {'type': 'user', 'message': {'model': 'claude-opus-9'}},
            {'type': 'assistant', 'message': {'model': '<synthetic>'}})) + '{torn')
        self.assertEqual(M.newest_model(folder), 'claude-opus-5-5')
        self.assertIsNone(M.newest_model(Path(self.tmp) / 'absent'))

    def test_model_named_rules_are_listed_by_both_spellings(self):
        root = ponytail_root(self.tmp)
        write(root / 'CLAUDE.md', 'a\nOpus 5.5 forgets the gate.\n')
        write(root / '.claude/skills/x/SKILL.md', 'use claude-opus-5-5 here\n')
        write(root / 'Projects/p/notes.md', 'Opus 5.5 is not a rule file\n')
        self.assertEqual(M.model_rule_lines(root, 'claude-opus-5-5'),
                         ['.claude/skills/x/SKILL.md:1', 'CLAUDE.md:2'])
        self.assertEqual(M.model_rule_lines(root, 'claude-haiku-4-5-20251001'), [])


class TrialFalseAlarms(Base):
    """Each case is a false alarm the trial on dashboard wave 4 (82480b6) found by hand."""

    def test_a_function_and_the_variable_holding_its_result_are_not_twins(self):
        self.silent('vague-name', 'a.js', 'function fileInfo(p) {\n  return p;\n}\nconst file = fileInfo(1);\n')
        self.silent('vague-name', 'a.py', 'def file_info(p):\n    return p\n\n\nfile = file_info(1)\n')
        self.fires('vague-name', 'b.py', 'file = 1\nfile_info = 2\n')

    def test_defaults_regex_bounds_and_http_codes_are_not_magic(self):
        self.silent('magic-number', 'a.js',
                    'export function a(p, { size = 2 * 1024 * 1024 } = {}) {}\n'
                    'export function b(p, { size = 2 * 1024 * 1024 } = {}) {}\n')
        self.silent('magic-number', 'b.js', 'const A = 1;\nconst x = /a{1,4096}/;\nconst y = /b{1,4096}/;\n')
        self.silent('magic-number', 'c.js', "send(res, 404, 'x');\nsend(res, 404, 'y');\n"
                    "throw httpError(404, 'z');\n")
        self.fires('magic-number', 'd.js', 'let a = 4096 + n;\nlet b = 4096 - n;\n')

    def test_a_prose_comment_quoting_code_is_not_code(self):
        self.silent('commented-code', 'a.js', '// A name and its value, in JSON, or bare: PASSWORD=x;\nlet a = 1;\n')
        self.fires('commented-code', 'b.js', '// let total = count + 1;\nlet a = 1;\n')

    def test_callers_come_only_from_code_in_the_same_language(self):
        self.repo.commit({'app.js': 'export function pick(x) {\n  return x;\n}\n',
                          'use.js': "import { pick } from './app.js';\npick(1);\n",
                          'notes.md': 'You pick a tool.\n', 'tool.py': 'pick = 3\n',
                          'bin/tool': '#!/usr/bin/env python3\nprint("pick one")\n'})
        self.repo.write('app.js', 'export function pick(x) {\n  return x + 1;\n}\n')
        code, out, _ = self.main('check')
        self.assertIn('use.js:2', out)
        self.assertNotIn('notes.md', out)
        self.assertNotIn('tool.py', out)
        self.assertNotIn('bin/tool', out)


if __name__ == '__main__':
    unittest.main()
