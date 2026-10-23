"""sync.sh, exercised against throwaway repositories.

Run with python3 -m unittest discover -s .claude/hooks -p 'test_*.py'.

In dev the syncer pulls and guards; it never commits and never pushes. The
start check runs `--pull`, which fast-forwards this checkout or says why it
did not, and the guards are what a commit is checked against. The old workspace's session-end
sweep and its reconcile, which committed whatever was in the tree, are gone:
the tests at the end prove no mode is left that could sweep.

None of this touches the real workspace. The syncer derives its root from its
own location, so every test runs a COPY placed at <sandbox>/ws/.claude/hooks/:
its lock and state file land in the sandbox, and every repository it is
pointed at is a temporary one. HOME is replaced as well, so no global git
configuration or hook can reach in.

Set DEVARNESS_SYNC_UNDER_TEST to point these tests at another copy of the script.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[2]
SYNC = Path(os.environ.get('DEVARNESS_SYNC_UNDER_TEST', SOURCE / '.claude/hooks/sync.sh'))

# Assembled from pieces on purpose. The portability guard greps committed
# executables for these shapes, and this file is a committed executable.
MAC_HOME = '/Us' + 'ers/someone'
LINUX_HOME = '/ho' + 'me/alice'
CONTAINER_HOME = '/ho' + 'me/node'

# A git with a slow network, placed first on PATH. The Nth fetch or push first
# sleeps for the Nth delay in SLOW_FETCH or SLOW_PUSH (the last delay repeats),
# then runs the real git; every other command goes straight through. The sleep
# gets none of the test's pipes, which subprocess.run would otherwise wait on
# after run_bounded kills this script, and the trap takes it down with it.
SLOW_GIT = r'''#!/bin/sh
sub=
skip=
for arg in "$@"; do
  if [ -n "$skip" ]; then skip=; continue; fi
  case "$arg" in
    -C|-c) skip=1 ;;
    -*) ;;
    *) sub=$arg; break ;;
  esac
done
case "$sub" in
  fetch) delays=$SLOW_FETCH ;;
  push) delays=$SLOW_PUSH ;;
  *) exec "$REAL_GIT" "$@" ;;
esac
n=$(($(cat "$SLOW_COUNTS/$sub.count" 2>/dev/null || echo 0) + 1))
echo "$n" > "$SLOW_COUNTS/$sub.count"
secs=0
i=0
for delay in $delays; do
  i=$((i + 1)); secs=$delay
  [ "$i" -lt "$n" ] || break
done
if [ "$secs" -gt 0 ]; then
  trap 'kill $pid 2>/dev/null; exit 143' TERM
  sleep "$secs" </dev/null >/dev/null 2>&1 &
  pid=$!
  wait $pid
  trap - TERM
fi
exec "$REAL_GIT" "$@"
'''


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.hooks = self.root / 'ws/.claude/hooks'
        self.hooks.mkdir(parents=True)
        self.sync = self.hooks / 'sync.sh'
        shutil.copy2(SYNC, self.sync)
        home = self.root / 'home'
        home.mkdir()
        self.env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(home),
                    'GIT_CONFIG_NOSYSTEM': '1', 'LANG': 'C', 'TMPDIR': str(self.root)}

    def git(self, repo, *args, check=True):
        return subprocess.run(['git', '-C', str(repo), *args], env=self.env,
                              capture_output=True, text=True, check=check)

    def identify(self, path):
        for key, value in (('user.email', 'test@example.invalid'), ('user.name', 'test'),
                           ('commit.gpgsign', 'false')):
            self.git(path, 'config', key, value)

    def repo(self, name='work'):
        path = self.root / name
        path.mkdir(exist_ok=True)
        self.git(path, 'init', '-q', '-b', 'main')
        self.identify(path)
        (path / 'base.txt').write_text('line one\n')
        self.git(path, 'add', '.')
        self.git(path, 'commit', '-qm', 'base')
        return path

    def bare(self, name='origin.git'):
        path = self.root / name
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(path)],
                       env=self.env, capture_output=True, check=True)
        return path

    def clone(self, remote, name):
        path = self.root / name
        subprocess.run(['git', 'clone', '-q', str(remote), str(path)],
                       env=self.env, capture_output=True, check=True)
        self.identify(path)
        return path

    def workspace(self, remote=True):
        """<sandbox>/ws, the checkout the copied syncer derives, published to a bare origin."""
        ws = self.root / 'ws'
        (ws / '.gitignore').write_text('.claude/hooks/\n')
        self.repo('ws')
        if not remote:
            return None, ws
        origin = self.bare()
        self.git(ws, 'remote', 'add', 'origin', str(origin))
        self.git(ws, 'push', '-q', '-u', 'origin', 'main')
        return origin, ws

    def upstream_commit(self, origin, name='from-other.md', body='pushed elsewhere\n'):
        """Another device pushes one commit to origin; returns its hash."""
        other = self.root / 'other'
        if not other.exists():
            self.clone(origin, 'other')
        self.git(other, 'pull', '-q', '--ff-only')
        (other / name).write_text(body)
        self.git(other, 'add', name)
        self.git(other, 'commit', '-qm', 'other device: ' + name)
        self.git(other, 'push', '-q', 'origin', 'main')
        return self.head(other)

    def sync_run(self, *args):
        # Windows cannot execute a shell script by its path; Git's bash can.
        shell = [shutil.which('bash')] if os.name == 'nt' else []
        return subprocess.run([*shell, str(self.sync), *args], env=self.env,
                              capture_output=True, text=True, timeout=180)

    def state(self):
        path = self.hooks / 'sync.state'
        return path.read_text() if path.exists() else ''

    def head(self, repo, ref='HEAD'):
        return self.git(repo, 'rev-parse', ref).stdout.strip()


class SecretGuardTests(Sandbox):
    def test_secret_shaped_files_are_refused_and_named(self):
        for name in ('.env', 'config/.env', 'id_rsa', 'deploy.pem', 'auth.json',
                     'credentials.json'):
            with self.subTest(file=name):
                repo = self.repo(f'secret-{name.replace("/", "_")}')
                target = repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('KEY=value\n')
                done = self.sync_run('--guard-secrets', str(repo))
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(name, done.stderr)

    def test_a_committed_secret_is_still_refused(self):
        repo = self.repo()
        (repo / 'auth.json').write_text('{}\n')
        self.git(repo, 'add', 'auth.json')
        self.git(repo, 'commit', '-qm', 'oops')
        done = self.sync_run('--guard-secrets', str(repo))
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn('auth.json', done.stderr)

    def test_an_ignored_file_is_not_the_guards_business(self):
        repo = self.repo()
        (repo / '.gitignore').write_text('.env\n')
        (repo / '.env').write_text('KEY=value\n')
        done = self.sync_run('--guard-secrets', str(repo))
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_example_env_files_are_not_secrets(self):
        repo = self.repo()
        (repo / '.env.example').write_text('KEY=\n')
        done = self.sync_run('--guard-secrets', str(repo))
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_a_secret_inside_a_new_untracked_directory_is_still_seen(self):
        """Without --untracked-files=all git reports only `newdir/`.

        Every guard then drops it on its `[ -f ]` test and the whole subtree
        goes unchecked. Measured on 2026-09-09: 117 files were invisible to the
        guards that way, eight of them holding machine paths.
        """
        repo = self.repo()
        nested = repo / 'newdir/deeper'
        nested.mkdir(parents=True)
        (nested / '.env').write_text('KEY=value\n')
        done = self.sync_run('--guard-secrets', str(repo))
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn('newdir/deeper/.env', done.stderr)


class SizeGuardTests(Sandbox):
    def test_a_file_over_fifty_megabytes_is_refused(self):
        repo = self.repo()
        with open(repo / 'huge.bin', 'wb') as stream:
            stream.truncate(52_428_801)          # sparse: costs no disk
        done = self.sync_run('--guard-size', str(repo))
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn('huge.bin', done.stderr)

    def test_an_ordinary_file_passes(self):
        repo = self.repo()
        (repo / 'small.txt').write_text('x' * 1024)
        self.assertEqual(self.sync_run('--guard-size', str(repo)).returncode, 0)


class PortabilityGuardTests(Sandbox):
    def test_a_machine_path_in_an_executable_is_refused(self):
        for label, path in (('macOS home', MAC_HOME), ('Linux home', LINUX_HOME)):
            with self.subTest(path=label):
                repo = self.repo(f'port-{label.split()[0]}')
                (repo / 'tool.sh').write_text(f'#!/bin/sh\nexec {path}/bin/thing\n')
                done = self.sync_run('--check-portability', str(repo))
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn('tool.sh', done.stderr)

    def test_a_committed_machine_path_is_still_refused(self):
        # The guard reads the whole tree, not git status: committing must not hide a path.
        repo = self.repo()
        (repo / 'run.sh').write_text(f'#!/bin/sh\nexec {MAC_HOME}/tool.py\n')
        self.git(repo, 'add', 'run.sh')
        self.git(repo, 'commit', '-qm', 'run')
        done = self.sync_run('--check-portability', str(repo))
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn('run.sh', done.stderr)

    def test_the_checkers_that_spell_out_the_patterns_are_exempt(self):
        for relative in ('Harness/publish-check.py', 'Harness/tests/test_publish_check.py',
                         '.claude/hooks/guard_vendor_code.py', '.claude/hooks/test_guard_vendor_code.py'):
            with self.subTest(file=relative):
                repo = self.repo('checker-' + relative.replace('/', '_'))
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f'PATTERN = "{MAC_HOME}/x"\n')
                done = self.sync_run('--check-portability', str(repo))
                self.assertEqual(done.returncode, 0, done.stderr)

    def test_a_runtime_lookup_makes_the_same_path_portable(self):
        repo = self.repo()
        (repo / 'tool.sh').write_text(
            '#!/bin/sh\nHERE="$(cd "$(dirname "$0")" && pwd)"\n'
            f'[ -d "$HERE" ] || HERE={MAC_HOME}/fallback\n')
        self.assertEqual(self.sync_run('--check-portability', str(repo)).returncode, 0)

    def test_documents_that_quote_paths_as_evidence_are_exempt(self):
        for relative in ('Setup/superpowers/specs/design.md', 'CLAUDE.md',
                         'sub/_review/log.md', 'Harness/INSTALL.md', 'board.kicad_pcb',
                         'PRDs and Specs/003 Tool/evidence/run.json'):
            with self.subTest(file=relative):
                repo = self.repo('exempt-' + relative.replace('/', '_'))
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f'Evidence: ran from {MAC_HOME}/dev\n')
                done = self.sync_run('--check-portability', str(repo))
                self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_container_home_is_documentation_not_a_machine_path(self):
        repo = self.repo()
        (repo / 'compose.yaml').write_text(f'volumes:\n  - data:{CONTAINER_HOME}/.n8n\n')
        self.assertEqual(self.sync_run('--check-portability', str(repo)).returncode, 0)


class GitStateGuardTests(Sandbox):
    def test_an_interrupted_git_operation_refuses_the_whole_transaction(self):
        for marker, is_dir, reason in (('rebase-merge', True, 'mid-rebase'),
                                       ('index.lock', False, 'index.lock'),
                                       ('MERGE_HEAD', False, 'mid-merge')):
            with self.subTest(marker=marker):
                repo = self.repo(f'state-{marker}')
                path = repo / '.git' / marker
                path.mkdir() if is_dir else path.write_text('')
                done = self.sync_run('--guard-state', str(repo))
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(reason, done.stderr)


class PullTests(Sandbox):
    """`--pull` fast-forwards or says why not, and never writes anything of its own."""

    def commits(self, repo):
        return int(self.git(repo, 'rev-list', '--count', 'HEAD').stdout)

    def test_a_clean_checkout_behind_origin_is_fast_forwarded(self):
        origin, ws = self.workspace()
        theirs = self.upstream_commit(origin)
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.head(ws), theirs)
        self.assertIn('fast-forwarded 1 commit(s)', done.stderr)

    def test_uncommitted_work_is_never_swept_and_still_arrives_beside_the_pull(self):
        origin, ws = self.workspace()
        theirs = self.upstream_commit(origin)
        (ws / 'notes.md').write_text('half written\n')
        (ws / 'base.txt').write_text('line one, edited here\n')
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.head(ws), theirs, 'the pull did not arrive')
        status = self.git(ws, 'status', '--porcelain').stdout
        self.assertIn('notes.md', status, 'an untracked file was swept into a commit')
        self.assertIn('base.txt', status, 'an edit was swept into a commit')
        self.assertEqual(self.head(origin, 'main'), theirs, 'the pull pushed something')

    def test_local_commits_are_never_pushed(self):
        origin, ws = self.workspace()
        published = self.head(origin, 'main')
        (ws / 'mine.md').write_text('committed by path, not yet pushed\n')
        self.git(ws, 'add', 'mine.md')
        self.git(ws, 'commit', '-qm', 'mine')
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.head(origin, 'main'), published, 'the pull pushed a commit')
        self.assertIn('1 unpushed', self.sync_run('--status').stdout)

    def test_a_diverged_branch_is_left_exactly_as_it_is(self):
        origin, ws = self.workspace()
        theirs = self.upstream_commit(origin)
        (ws / 'mine.md').write_text('mine\n')
        self.git(ws, 'add', 'mine.md')
        self.git(ws, 'commit', '-qm', 'mine')
        mine = self.head(ws)
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn('diverged', done.stderr)
        self.assertEqual(self.head(ws), mine, 'a diverged branch was moved')
        self.assertFalse((ws / '.git/rebase-merge').exists(), 'a rebase was started')
        self.assertFalse((ws / '.git/MERGE_HEAD').exists(), 'a merge was started')
        self.assertEqual(self.head(origin, 'main'), theirs, 'the remote was rewritten')
        self.assertIn('diverged', self.state())

    def test_a_local_edit_in_the_way_stops_the_pull_without_touching_it(self):
        origin, ws = self.workspace()
        self.upstream_commit(origin, 'base.txt', 'line one, as the other device wrote it\n')
        before = self.head(ws)
        (ws / 'base.txt').write_text('line one, as this device wrote it\n')
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn('local edits are in the way', done.stderr)
        self.assertEqual(self.head(ws), before)
        self.assertEqual((ws / 'base.txt').read_text(), 'line one, as this device wrote it\n')

    def test_no_remote_is_a_note_and_changes_nothing(self):
        _, ws = self.workspace(remote=False)
        (ws / 'notes.md').write_text('local only\n')
        before = self.commits(ws)
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('no remote', done.stderr)
        self.assertEqual(self.commits(ws), before, 'a commit was made')
        self.assertIn('notes.md', self.git(ws, 'status', '--porcelain').stdout)
        status = self.sync_run('--status').stdout
        self.assertIn('no remote', status)
        self.assertIn('1 uncommitted', status)

    def test_an_unreachable_origin_is_offline(self):
        _, ws = self.workspace()
        self.git(ws, 'remote', 'set-url', 'origin', str(self.root / 'gone.git'))
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn('offline', self.state())
        self.assertIn('offline', self.sync_run('--status').stdout)

    def test_an_interrupted_git_operation_refuses_the_pull(self):
        _, ws = self.workspace()
        (ws / '.git/MERGE_HEAD').write_text('')
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn('REFUSED', self.state())

    def test_a_pause_file_stops_the_pull(self):
        origin, ws = self.workspace()
        before = self.head(ws)
        self.upstream_commit(origin)
        (self.hooks / 'sync.off').write_text('')
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.head(ws), before)
        self.assertIn('PAUSED', self.sync_run('--status').stdout)

    def test_no_mode_is_left_that_could_sweep_or_push(self):
        """The old workspace's --hook-end, --reconcile and --push committed whatever was in the tree."""
        origin, ws = self.workspace()
        before, published = self.head(ws), self.head(origin, 'main')
        (ws / 'notes.md').write_text('half written\n')
        for mode in ('--hook-end', '--hook-start', '--reconcile', '--reconcile-one', '--push', '--archive'):
            with self.subTest(mode=mode):
                done = self.sync_run(mode)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn('unknown mode', done.stderr)
        self.assertEqual(self.head(ws), before)
        self.assertEqual(self.head(origin, 'main'), published)
        self.assertIn('notes.md', self.git(ws, 'status', '--porcelain').stdout)
        # And at the source: no git command that writes history is left in the script.
        for line in self.sync.read_text(encoding='utf-8').splitlines():
            code = line.strip()
            if code.startswith('#') or 'log "' in code:
                continue
            self.assertNotRegex(code, r'\bgit\b.*\s(add|commit|push|rebase|reset|stash)\b', code)


class LockTests(Sandbox):
    def test_a_live_lock_is_never_broken_however_old(self):
        """Age is not death: a sleeping laptop can hold a live lock for hours."""
        self.workspace()
        lock = self.hooks / '.sync.lock'
        lock.mkdir()
        pid = os.getpid()                                   # this process: alive
        if os.name == 'nt':
            # Git's bash cannot see a Windows pid, only its own; the real lock holder is always bash.
            sleeper = subprocess.Popen([shutil.which('bash'), '-c', 'echo $$; exec sleep 120'],
                                       stdout=subprocess.PIPE, text=True)
            self.addCleanup(sleeper.kill)
            pid = int(sleeper.stdout.readline())
        (lock / 'pid').write_text(f'{pid}\n')
        old = 1_000_000_000                                 # 2001
        os.utime(lock, (old, old))
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 4, done.stderr)
        self.assertTrue((lock / 'pid').exists(), 'a live lock was broken')

    def test_a_lock_left_by_a_dead_process_is_cleared(self):
        origin, ws = self.workspace()
        theirs = self.upstream_commit(origin)
        finished = subprocess.Popen(['true'])
        finished.wait()
        lock = self.hooks / '.sync.lock'
        lock.mkdir()
        (lock / 'pid').write_text(f'{finished.pid}\n')
        done = self.sync_run('--pull')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.head(ws), theirs)


class NetworkBoundTests(Sandbox):
    """The start's pull waits longer for the network, inside a deadline.

    session_start.py runs `--pull` under a 100 s bound and reads an overrun as
    START FAILED. Fetches were measured at 5.0, 5.8 and 85.9 s, and an 8 s
    bound read a reachable GitHub as offline, so each call gets 20 s and one
    retry, and an 80 s deadline over all calls keeps that inside the bound.
    The slow network is SLOW_GIT.
    """

    def slow_network(self, fetch='', push=''):
        """The environment that puts SLOW_GIT first on PATH with these delays."""
        shims = self.root / 'shims'
        shims.mkdir()
        with (shims / 'git').open('w', newline='\n') as handle:
            handle.write(SLOW_GIT)
        (shims / 'git').chmod(0o755)
        # The git binary itself, from its exec path. macOS's /usr/bin/git is an
        # xcrun trampoline that took 0.3 s a call when SLOW_GIT started it.
        found = shutil.which('git', path=self.env['PATH'])
        exec_path = subprocess.run([found, '--exec-path'], env=self.env, capture_output=True,
                                   text=True).stdout.strip()
        real = shutil.which('git', path=exec_path) or found
        env = {'PATH': str(shims) + os.pathsep + self.env['PATH'], 'REAL_GIT': real,
               'SLOW_COUNTS': str(shims), 'SLOW_FETCH': fetch, 'SLOW_PUSH': push}
        if os.name == 'nt':
            # Restore the shim after Git Bash prepends its own bin directories.
            startup = self.root / 'bash-env.sh'
            with startup.open('w', newline='\n') as handle:
                handle.write('export PATH="$(cygpath -u "$SLOW_COUNTS"):$PATH"\n')
            env['BASH_ENV'] = str(startup)
        return env

    def started(self, command):
        """How many times the syncer started `git fetch`."""
        count = self.root / 'shims' / f'{command}.count'
        return int(count.read_text()) if count.exists() else 0

    def timed_sync(self, *args, **env):
        """Run the syncer with this environment added; return its result and seconds."""
        saved = self.env
        self.env = {**saved, **env}
        began = time.monotonic()
        try:
            done = self.sync_run(*args)
        finally:
            self.env = saved
        return done, time.monotonic() - began

    def test_an_override_that_is_not_whole_seconds_falls_back_to_its_default(self):
        """`20s` would make run_bounded's comparison fail and the bound never fire."""
        self.workspace()
        done, _ = self.timed_sync('--status', DEVARNESS_SYNC_START_TIMEOUT='',
                                  DEVARNESS_SYNC_START_DEADLINE='80.5')
        self.assertIn('DEVARNESS_SYNC_START_DEADLINE=80.5 is not whole seconds; using 80', done.stderr)
        self.assertNotIn('DEVARNESS_SYNC_START_TIMEOUT', done.stderr, 'an empty override is the default, not an error')

    def test_a_fetch_that_times_out_once_is_retried_and_succeeds(self):
        """The first fetch outlives its 2 s bound; the retry answers at once."""
        origin, ws = self.workspace()
        theirs = self.upstream_commit(origin)
        done, _ = self.timed_sync('--pull', DEVARNESS_SYNC_START_TIMEOUT='2', **self.slow_network(fetch='30 0'))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.started('fetch'), 2)
        self.assertIn('dev fetch timed out after 2s; retrying once', done.stderr)
        self.assertEqual(self.head(ws), theirs, 'the pull did not arrive')

    def test_a_fetch_that_never_answers_stops_at_the_deadline(self):
        """Every fetch silent for 30 s, 15 s per call, a 4 s deadline: offline, fast, no retry."""
        self.workspace()
        done, seconds = self.timed_sync('--pull', DEVARNESS_SYNC_START_TIMEOUT='15',
                                        DEVARNESS_SYNC_START_DEADLINE='4', **self.slow_network(fetch='30'))
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(self.started('fetch'), 1, 'a network call started after the deadline')
        self.assertLess(seconds, 10, 'the first call was not clipped to the deadline')
        self.assertIn('dev\tlast_error\toffline', self.state())

    def test_the_start_bound_is_twenty_seconds_when_nothing_overrides_it(self):
        """No DEVARNESS_SYNC_START_TIMEOUT: the retry log must name 20.

        Only the deadline is overridden, and only to keep this test to about
        25 s (35 s on Windows): with 20 s for the first call and time left for
        the retry, it still proves the first bound.
        """
        self.workspace()
        # Windows starts the first fetch 2.6 s in and takes 2.5 s to end one
        # that timed out, so the retry is decided 25.1 s in (measured
        # 2026-09-19): a 25 s deadline left it no room there.
        deadline = '35' if os.name == 'nt' else '25'
        done, seconds = self.timed_sync('--pull', DEVARNESS_SYNC_START_DEADLINE=deadline,
                                        **self.slow_network(fetch='30'))
        self.assertIn('dev fetch timed out after 20s; retrying once', done.stderr)
        self.assertLess(seconds, 45, 'the first call did not use the 20 s default')
        # The 80 s deadline cannot be proved without waiting 80 s, so it is pinned at
        # the source: session_start.py bounds --pull at 100 s and reads an
        # overrun as START FAILED, which is what these two literals protect.
        script = (Path(__file__).resolve().parent / 'sync.sh').read_text(encoding='utf-8')
        self.assertIn('START_DEADLINE="${DEVARNESS_SYNC_START_DEADLINE:-80}"', script)
        self.assertIn('START_TIMEOUT="${DEVARNESS_SYNC_START_TIMEOUT:-20}"', script)


if __name__ == '__main__':
    unittest.main()
