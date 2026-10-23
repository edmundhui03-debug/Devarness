"""Run with python3 -m unittest discover -s .claude/hooks -p 'test_*.py'.

The start check: preflight, then a fast-forward-only pull, then START
COMPLETE, DEGRADED or FAILED. Fixtures keep every pull and client launch out
of the real workspace.
"""
import json
import importlib.util
import os
from pathlib import Path
import runpy
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2]


def shell(command):
    """The argv that runs a script: by path on POSIX, through Git Bash on Windows.

    Windows cannot execute a script by path (WinError 193). The hook hands its
    own scripts to Git Bash's bash (session_start._launchable), and the tests
    do the same; where only WSL's bash, in System32, is on PATH they skip.
    """
    command = [str(part) for part in command]
    return command if os.name != "nt" else [git_bash()] + command


def git_bash():
    bash = shutil.which("bash")
    if not bash or "system32" in os.path.normcase(bash):
        raise unittest.SkipTest("Git Bash's bash is not on PATH")
    return bash


def bare_path():
    """A PATH holding the shell's own tools and python3, and nothing installed later.

    The Mac's system folders hold both. On Windows python3 has a folder of
    its own and the shell's tools are in Git's usr/bin, so those two are kept.
    """
    if os.name != "nt":
        return "/usr/bin:/bin:/usr/sbin:/sbin"
    python3 = shutil.which("python3")
    if not python3:
        raise unittest.SkipTest("python3 is not on PATH")
    return os.pathsep.join([os.path.dirname(python3), os.path.dirname(git_bash())])


PREFLIGHT_OK = "printf '%s\\n' '" + json.dumps({
    "systemMessage": "START ready\n  cship ready\nRouter: CLAUDE.md",
    "additionalContext": "router context"}) + "'\nprintf 'preflight\\n' >> \"$TEST_EVENTS\""


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="start-check-tests-")
        self.addCleanup(self.tmp.cleanup)
        # resolve(): TEMP may hold an 8.3 short name, while the launchers
        # report the long path they resolved.
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "workspace with spaces"
        self.hooks = self.root / ".claude/hooks"
        self.bin = self.root / "Harness/bin"
        self.hooks.mkdir(parents=True)
        self.bin.mkdir(parents=True)
        for name in ("session-start.sh", "session_start.py"):
            shutil.copy2(SOURCE / ".claude/hooks" / name, self.hooks / name)
        for name in ("codex-start", "claude-start", "start-check", "statusline"):
            shutil.copy2(SOURCE / "Harness/bin" / name, self.bin / name)
        self.event = self.base / "events"
        self.env = dict({k: v for k, v in os.environ.items() if k != 'DEVARNESS_START_GATE_DONE'}, TEST_EVENTS=str(self.event))
        self.write(self.hooks / "preflight.sh", PREFLIGHT_OK)
        self.sync()

    def write(self, path, body):
        path.write_text("#!/usr/bin/env bash\n" + body + "\n")
        path.chmod(0o755)

    def sync(self, rc=0, says="sync: dev up to date with origin/main"):
        """A sync.sh stub: records the mode it was asked for, says a line, exits rc."""
        self.write(self.hooks / "sync.sh", """if [ "$1" = --status ]; then
printf 'saved status only\\n'
exit 0
fi
printf 'pull-start %s\\n' "$1" >> "$TEST_EVENTS"
sleep 0.05
printf 'pull-end\\n' >> "$TEST_EVENTS"
printf '%s\\n' '""" + says + """' >&2
exit """ + str(rc))

    def gate(self, *args):
        return subprocess.run(shell([self.hooks / "session-start.sh", *args]),
                              input="{}", capture_output=True, text=True,
                              cwd=self.base, env=self.env, timeout=5)

    def test_hook_waits_for_the_pull_and_returns_event_context(self):
        p = self.gate()
        d = json.loads(p.stdout)
        self.assertIn("START COMPLETE — READY", d["systemMessage"])
        self.assertTrue(d["continue"])
        self.assertIn("router context", d["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.event.read_text().splitlines(), ["preflight", "pull-start --pull", "pull-end"])

    def test_the_start_asks_for_a_pull_and_nothing_else(self):
        # dev has no sweep: the only mode the start may ask of sync.sh is
        # --pull (or --status in check mode). update-tools, which commits and
        # pushes pins, is not run by the start either; it runs daily or on demand.
        (self.bin / "update-tools").write_text(
            "import os, sys\nopen(os.environ['TEST_EVENTS'], 'a').write('update-tools ' + ' '.join(sys.argv[1:]) + '\\n')\n")
        self.assertEqual(self.gate("--text").returncode, 0)
        events = self.event.read_text().splitlines()
        self.assertEqual([e for e in events if e.startswith("pull-start")], ["pull-start --pull"])
        self.assertFalse([e for e in events if e.startswith("update-tools")], events)

    def test_a_missing_remote_is_a_note_not_degraded(self):
        self.sync(0, "sync: dev has no remote — nothing to pull; commits stay on this device")
        p = self.gate("--text")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("no remote", p.stdout)
        self.assertIn("START COMPLETE — READY", p.stdout)

    def test_a_line_that_is_not_utf8_never_fails_the_start(self):
        # Task 8 fix round 1, Minor 1: run() decoded strictly, and one byte a
        # child wrote in another encoding turned the start into START FAILED.
        self.write(self.hooks / "sync.sh", "printf 'sync: caf\\351 up to date\\n' >&2\nexit 0")
        p = self.gate("--text")
        self.assertIn("sync: caf� up to date", p.stdout)
        self.assertIn("START COMPLETE — READY", p.stdout)

    def test_check_does_not_pull(self):
        p = self.gate("--check", "--text")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.event.read_text().splitlines(), ["preflight"])
        self.assertIn("status only", p.stdout)

    def test_a_saved_status_that_says_offline_degrades_check_mode(self):
        self.write(self.hooks / "sync.sh",
                   "printf 'sync              dev 0 uncommitted, 2 unpushed - fetched 04:06 - offline 05:10\\n'")
        p = self.gate("--check", "--text")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("START COMPLETE — DEGRADED", p.stdout)

    def test_only_check_text_asks_the_preflight_for_every_row(self):
        # The healthy banner points at `start-check --check --text` for the list, so
        # that command must print it; the launchers and the Codex hook keep the count.
        self.write(self.hooks / "preflight.sh", "printf '%s\\n' '" + json.dumps({
            "systemMessage": "START ready\n  cship ready", "additionalContext": ""})
            + "'\nprintf 'all=%s\\n' \"${DEVARNESS_START_ALL:-}\" >> \"$TEST_EVENTS\"")
        for args, want in ((("--check", "--text"), "all=1"), (("--text",), "all="), (("--check",), "all=")):
            self.event.write_text("")
            self.gate(*args)
            self.assertEqual(self.event.read_text().splitlines()[0], want, args)

    def test_silent_preflight_names_itself_in_capitals(self):
        """Empty output used to surface as a bare JSON decode error; and an earlier
        round 'simplified away' the FAILED banner. It must stay loud."""
        self.write(self.hooks / "preflight.sh", "printf 'cannot create temp file\\n' >&2; exit 0")
        p = self.gate("--check", "--text")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("START FAILED", p.stdout)
        self.assertIn("preflight produced no output", p.stdout)
        self.assertIn("cannot create temp file", p.stdout)
        d = json.loads(self.gate().stdout)
        self.assertIn("START FAILED", d["systemMessage"])
        self.assertIn("START FAILED", d["hookSpecificOutput"]["additionalContext"])

    def test_bad_preflight_blocks_without_a_pull(self):
        for body in ("exit 0", "echo not-json", "echo '[]'", "echo '{}'", "exit 7"):
            with self.subTest(body=body):
                self.write(self.hooks / "preflight.sh", body)
                p = self.gate()
                self.assertIn("START FAILED", json.loads(p.stdout)["systemMessage"])
                d = json.loads(p.stdout)
                self.assertFalse(d["continue"])
                self.assertIn("stopReason", d)
                self.assertIn("START FAILED", d["hookSpecificOutput"]["additionalContext"])
                self.assertNotEqual(self.gate("--text").returncode, 0)
                self.assertFalse(self.event.exists())

    def test_a_refused_or_broken_pull_blocks(self):
        # 2 refused (mid-rebase, index.lock), 8 unknown: the gate refuses.
        for rc in (2, 8):
            with self.subTest(rc=rc):
                self.sync(rc, "sync: dev is mid-rebase")
                d = json.loads(self.gate().stdout)
                self.assertIn("START FAILED", d["systemMessage"])
                # Claude ignores `continue` from SessionStart; Codex may not.
                # Both must be emitted, and the model-facing context must say
                # FAILED regardless, because that is all Claude will see.
                self.assertFalse(d["continue"])
                self.assertIn("stopReason", d)
                self.assertIn("START FAILED", d["hookSpecificOutput"]["additionalContext"])
                self.assertIn("mid-rebase", d["systemMessage"])
                self.assertNotEqual(self.gate("--text").returncode, 0)

    def test_busy_is_degraded_not_fatal(self):
        # 4 means another pull or update-tools holds the lock: degraded, and allowed.
        self.sync(4)
        d = json.loads(self.gate().stdout)
        self.assertIn("START COMPLETE", d["systemMessage"])
        self.assertIn("DEGRADED", d["systemMessage"])
        self.assertEqual(self.gate("--text").returncode, 0)

    def test_offline_or_diverged_is_explicit_and_allows_local_work(self):
        for says in ("sync: dev — offline, working locally",
                     "sync: dev has diverged from origin/main — not pulled; nothing was changed"):
            with self.subTest(says=says):
                self.sync(1, says)
                d = json.loads(self.gate().stdout)
                self.assertIn("START COMPLETE", d["systemMessage"])
                self.assertIn("DEGRADED", d["systemMessage"])
                self.assertIn("local work only", d["systemMessage"])

    def test_timeout_does_not_leave_a_child_writing(self):
        spec = importlib.util.spec_from_file_location("start_check", self.hooks / "session_start.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        child = self.base / "slow.sh"
        marker = self.base / "late-write"
        ready = self.base / "ready"
        release = self.base / "release"
        stop = self.base / "stop"
        abort = self.base / "abort"
        # A write is permitted only after run() returns. A fixed sleep also
        # counted writes during Windows taskkill's own cleanup latency.
        worker = self.base / "worker.py"
        # Stable native children avoid MSYS fork/exec churn during taskkill.
        # Explicitly closed child pipes also make the no-cleanup control return.
        worker.write_text("""import subprocess, sys, time
from pathlib import Path
ready, release, stop, abort, marker = map(Path, sys.argv[2:])
if sys.argv[1] == 'parent':
    subprocess.Popen([sys.executable, __file__, 'worker', *sys.argv[2:]],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True,
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    while not stop.exists():
        time.sleep(0.01)
else:
    ready.touch()
    while not release.exists() and not abort.exists():
        time.sleep(0.01)
    if not abort.exists():
        marker.touch()
""", encoding="utf-8")
        self.write(child, "exec " + shlex.join([
            Path(sys.executable).as_posix(), worker.as_posix(), "parent",
            *(path.as_posix() for path in (ready, release, stop, abort, marker))]))
        communicate = subprocess.Popen.communicate
        kill_group = module._kill_group
        armed = False

        def after_ready(process, *args, **kwargs):
            nonlocal armed
            if not armed and process.args[-1] == str(child):
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if not ready.exists():
                    abort.touch()
                    try:
                        kill_group(process.pid, module.signal.SIGTERM)
                    finally:
                        stop.touch()
                    self.fail("the background worker did not become ready")
                armed = True
            return communicate(process, *args, **kwargs)

        def kill_then_release_parent(pid, sig):
            try:
                kill_group(pid, sig)
            finally:
                # Let the root exit even in a cleanup-disabled mutation; the
                # worker has separate pipes and still waits for release.
                stop.touch()

        try:
            with patch.object(subprocess.Popen, "communicate", after_ready), \
                    patch.object(module, "_kill_group", kill_then_release_parent):
                with self.assertRaisesRegex(RuntimeError, "timed out"):
                    module.run([str(child)], 0.05)
            self.assertTrue(armed)
            release.touch()
            deadline = time.monotonic() + 1
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(marker.exists(), "a child wrote after timeout cleanup returned")
        finally:
            abort.touch()
            stop.touch()

    def test_wrapper_without_python3_still_reports_failed_in_context(self):
        # session-start.sh has its own fallback when python3 is absent. It
        # must carry additionalContext, because for Claude that is the only
        # field that reaches the model; a systemMessage alone is a banner the
        # agent never reads.
        bindir = Path(tempfile.mkdtemp())
        for tool in ("bash", "sh", "dirname", "printf"):
            path = shutil.which(tool)
            if path:
                (bindir / tool).symlink_to(path)
        p = subprocess.run(shell([self.hooks / "session-start.sh"]), input="{}", capture_output=True,
                           text=True, env={"PATH": str(bindir), "HOME": str(bindir)})
        self.assertEqual(p.returncode, 0)
        d = json.loads(p.stdout)
        self.assertFalse(d["continue"])
        # Only the wrapper's own fallback says this; the gate's failure output
        # never mentions python3, so a passing assertion proves the branch ran.
        self.assertIn("python3", d["stopReason"])            # "The start check could not run: python3 missing"
        self.assertIn("python3 is not on PATH", d["hookSpecificOutput"]["additionalContext"])
        shutil.rmtree(bindir, ignore_errors=True)

    def test_launcher_marker_fresh_means_status_only(self):
        # A launcher gate that ended READY exports the time; within five minutes
        # the hook must report status and NOT pull again.
        env = {"DEVARNESS_START_GATE_DONE": str(int(time.time()))}
        p = subprocess.run([sys.executable, str(self.hooks / "session_start.py"), "--text"],
                           input="{}", capture_output=True, text=True, env=dict(self.env, **env))
        self.assertIn("status only", p.stdout)
        self.assertNotIn("pull-start", self.event.read_text())

    def test_launcher_marker_stale_or_garbage_pulls(self):
        for value in (str(int(time.time()) - 600), "not-a-number", ""):
            with self.subTest(value=value):
                self.event.write_text("")
                p = subprocess.run([sys.executable, str(self.hooks / "session_start.py"), "--text"],
                                   input="{}", capture_output=True, text=True,
                                   env=dict(self.env, DEVARNESS_START_GATE_DONE=value))
                self.assertNotIn("status only", p.stdout)
                self.assertIn("pull-start", self.event.read_text())

    def test_launchers_resolve_symlinks_wait_and_preserve_arguments(self):
        external = self.base / "installed bin"
        external.mkdir()
        self.env["PATH"] = str(external) + os.pathsep + os.environ["PATH"]
        for client in ("codex", "claude"):
            with self.subTest(client=client):
                self.write(external / client, 'printf "client:%s:%s:%s\\n" "$(pwd -W 2>/dev/null || pwd)" "$1" "$2" >> "$TEST_EVENTS"')
                (external / (client + "-start")).symlink_to(self.bin / (client + "-start"))
                self.event.unlink(missing_ok=True)
                p = subprocess.run(shell([external / (client + "-start"), "argument with spaces", "--flag"]),
                                   env=self.env, cwd=self.base, capture_output=True, text=True, timeout=5)
                self.assertEqual(p.returncode, 0, p.stderr)
                events = self.event.read_text().splitlines()
                self.assertEqual(events[:3], ["preflight", "pull-start --pull", "pull-end"])
                self.assertEqual(events[3].replace("/", os.sep), "client:{}:argument with spaces:--flag".format(self.root))
                self.sync(2, "sync: dev is mid-rebase")
                self.event.unlink()
                p = subprocess.run(shell([external / (client + "-start")]), env=self.env,
                                   cwd=self.base, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(p.returncode, 0)
                self.assertNotIn("client:", self.event.read_text())
                self.sync()


class RealPullTests(unittest.TestCase):
    """The start with the real sync.sh, against a throwaway checkout and origin.

    What the owner asked for, as behaviour: the start brings this checkout up to
    origin, sweeps nothing into a commit, pushes nothing, and a checkout with no
    remote starts READY.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="start-check-pull-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.ws = self.base / "dev"
        hooks = self.ws / ".claude/hooks"
        hooks.mkdir(parents=True)
        for name in ("session-start.sh", "session_start.py", "sync.sh"):
            shutil.copy2(SOURCE / ".claude/hooks" / name, hooks / name)
        self.event = self.base / "events"
        home = self.base / "home"
        home.mkdir()
        self.env = dict({k: v for k, v in os.environ.items() if k != "DEVARNESS_START_GATE_DONE"},
                        TEST_EVENTS=str(self.event), HOME=str(home), GIT_CONFIG_NOSYSTEM="1")
        (hooks / "preflight.sh").write_text("#!/usr/bin/env bash\n" + PREFLIGHT_OK + "\n")
        (self.ws / ".gitignore").write_text(".claude/hooks/\n")
        (self.ws / "base.txt").write_text("line one\n")
        self.git(self.ws, "init", "-q", "-b", "main")
        self.identify(self.ws)
        self.git(self.ws, "add", ".")
        self.git(self.ws, "commit", "-qm", "base")

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], env=self.env,
                              capture_output=True, text=True, check=True).stdout.strip()

    def identify(self, repo):
        for key, value in (("user.email", "test@example.invalid"), ("user.name", "test"),
                           ("commit.gpgsign", "false")):
            self.git(repo, "config", key, value)

    def start(self):
        return subprocess.run(shell([self.ws / ".claude/hooks/session-start.sh", "--text"]),
                              capture_output=True, text=True, env=self.env, timeout=120,
                              stdin=subprocess.DEVNULL)

    def test_no_remote_starts_ready_and_commits_nothing(self):
        (self.ws / "notes.md").write_text("half written\n")
        p = self.start()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("no remote", p.stdout)
        self.assertIn("START COMPLETE — READY", p.stdout)
        self.assertEqual(self.git(self.ws, "rev-list", "--count", "HEAD"), "1")
        self.assertIn("notes.md", self.git(self.ws, "status", "--porcelain"))

    def test_the_start_fast_forwards_and_sweeps_and_pushes_nothing(self):
        origin = self.base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                       env=self.env, capture_output=True, check=True)
        self.git(self.ws, "remote", "add", "origin", str(origin))
        self.git(self.ws, "push", "-q", "-u", "origin", "main")
        other = self.base / "other"
        subprocess.run(["git", "clone", "-q", str(origin), str(other)], env=self.env,
                       capture_output=True, check=True)
        self.identify(other)
        (other / "theirs.md").write_text("from the other device\n")
        self.git(other, "add", "theirs.md")
        self.git(other, "commit", "-qm", "theirs")
        self.git(other, "push", "-q", "origin", "main")
        theirs = self.git(other, "rev-parse", "HEAD")
        (self.ws / "notes.md").write_text("half written\n")
        p = self.start()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("START COMPLETE — READY", p.stdout)
        self.assertEqual(self.git(self.ws, "rev-parse", "HEAD"), theirs, "the pull did not arrive")
        self.assertIn("notes.md", self.git(self.ws, "status", "--porcelain"), "work was swept")
        self.assertEqual(self.git(origin, "rev-parse", "main"), theirs, "the start pushed")


class SettingsTests(unittest.TestCase):
    """dev registers the start check and no session-end sync."""

    def settings(self):
        return json.loads((SOURCE / ".claude/settings.json").read_text(encoding="utf-8"))

    def test_no_session_end_sync_is_registered(self):
        hooks = self.settings()["hooks"]
        self.assertNotIn("SessionEnd", hooks)
        self.assertNotIn("sync", json.dumps(hooks))

    def test_the_start_check_runs_at_session_start(self):
        commands = [h["command"] for group in self.settings()["hooks"]["SessionStart"] for h in group["hooks"]]
        self.assertEqual(commands, ['"$CLAUDE_PROJECT_DIR"/.claude/hooks/session-start.sh'])

    def test_codex_hooks_start_from_python3(self):
        # Codex runs hook commands through Windows PowerShell, which cannot start
        # an extensionless script and whose bash is WSL's.
        hooks = json.loads((SOURCE / ".codex/hooks.json").read_text(encoding="utf-8"))["hooks"]
        for event in hooks.values():
            for group in event:
                for hook in group["hooks"]:
                    self.assertTrue(hook["command"].startswith("python3 "), hook["command"])


def degrading_lines(source):
    """Line numbers where video-study or the Managed Agents lab could add to `degraded`."""
    import ast
    found = []

    def is_degraded_append(node):
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'append' and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'degraded')

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.If):
            names = {item.id for item in ast.walk(node.test) if isinstance(item, ast.Name)}
            if names & {'cma_ok', 'watch_ok'} and any(is_degraded_append(item) for item in ast.walk(node)):
                found.append(node.lineno)
        if is_degraded_append(node) and ('video-study' in ast.dump(node) or 'managed-agents' in ast.dump(node)):
            found.append(node.lineno)
    return sorted(set(found))


SANDBOX = shutil.which("sandbox-exec")
NO_WRITES = ('(version 1)(allow default)(deny file-write* (subpath "/private") '
             '(subpath "/var") (subpath "/tmp") (subpath "/Users") (subpath "/Volumes"))')


@unittest.skipUnless(sys.platform == "darwin" and SANDBOX, "macOS sandbox-exec is required")
class ReadOnlyCheckTests(unittest.TestCase):
    """`start-check --check` must work where nothing can be written.

    On 2026-09-14 Aster's review stopped in Codex's read-only sandbox with
    "FAILED — Expecting value: line 1 column 1". macOS /bin/bash 3.2 writes
    every here-document to a temporary file; the preflight fed its report
    program to python3 through one, so a sandbox that forbids writes gave
    python3 no program, the preflight printed nothing and still exited 0.
    A check that promises to be read-only has to run read-only.
    """

    def sandboxed(self, *command):
        return subprocess.run([SANDBOX, "-p", NO_WRITES, *command], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60, cwd=SOURCE)

    def test_preflight_reports_valid_json_without_writes(self):
        done = self.sandboxed(str(SOURCE / ".claude/hooks/preflight.sh"))
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        self.assertNotIn("here document", done.stderr)
        report = json.loads(done.stdout)
        self.assertTrue(report["systemMessage"].startswith("START ready\n"))

    def test_saved_sync_status_is_not_blank_without_writes(self):
        done = self.sandboxed(str(SOURCE / ".claude/hooks/sync.sh"), "--status")
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        self.assertNotIn("here document", done.stderr)
        self.assertRegex(done.stdout, r"sync +\S")

    def test_whole_check_gate_is_ready_without_writes(self):
        done = self.sandboxed(str(SOURCE / ".claude/hooks/session-start.sh"), "--check", "--text")
        self.assertEqual(done.returncode, 0, done.stdout[-600:])
        self.assertIn("START COMPLETE", done.stdout)


class InjectedContextTests(unittest.TestCase):
    """The context preflight injects is the first thing every session reads.

    It is assembled by concatenating string literals, which is exactly the
    shape that breaks silently: on 2026-09-12 a new clause was inserted after
    the opening fragment of an existing sentence instead of before it, so every
    session for a day read a mangled sentence. Nothing failed, because a
    mangled sentence is still valid JSON.
    """

    def context(self) -> str:
        preflight = SOURCE / '.claude/hooks/preflight.sh'
        done = subprocess.run(shell([preflight]), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        return json.loads(done.stdout)['additionalContext']

    def test_no_house_rule_is_stated_twice(self):
        text = self.context()
        for rule in ('The start check is active for this workspace',
                     'GRILL FIRST',
                     'finding on trust',
                     'md-pages'):
            with self.subTest(rule=rule):
                self.assertEqual(text.count(rule), 1,
                                 f'{rule!r} appears {text.count(rule)} times')

    def test_each_rule_still_reaches_its_object(self):
        """A spliced literal truncates a rule before it says anything useful,
        so each instruction must still name what it points at."""
        text = self.context()
        for rule, object_named in (
                ('Read CLAUDE.md', 'AGENTS.md'),
                ('convert a binary document', 'md-pages'),
                ('GRILL FIRST', 'grill-first'),
                ('never take a finding on trust', 'verify each one')):
            with self.subTest(rule=rule):
                start = text.find(rule)
                self.assertNotEqual(start, -1, f'{rule!r} is missing entirely')
                clause = text[start:start + 400]
                self.assertIn(object_named, clause,
                              f'{rule!r} never reaches {object_named!r} — truncated?')

    def test_it_still_says_the_things_that_matter(self):
        text = self.context()
        for claim in ('CLAUDE.md', 'AGENTS.md', '.pi/APPEND_SYSTEM.md', 'superpowers',
                      'PETER', 'ASTER', 'MAY', 'library', 'grill-first', 'md-pages'):
            with self.subTest(claim=claim):
                self.assertIn(claim, text)

    def test_missing_video_tools_are_reported_but_never_degrade_the_banner(self):
        """Run with yt-dlp and ffmpeg off PATH, the case a device without them hits."""
        preflight = SOURCE / '.claude/hooks/preflight.sh'
        env = dict(os.environ, PATH=bare_path())
        env.pop('DEVARNESS_ORIG_PATH', None)
        done = subprocess.run(shell([preflight]), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60, env=env)
        message = json.loads(done.stdout)['systemMessage']
        rows = [line.strip() for line in message.splitlines()]
        watch = [row for row in rows if row.startswith('video-study ')]
        self.assertEqual(len(watch), 1, message[-800:])
        self.assertIn('unavailable', watch[0])
        for row in rows:
            if row.startswith('Degraded:'):
                self.assertNotIn('video-study', row)

    def test_no_readiness_result_for_the_opt_in_tools_feeds_degraded(self):
        """The lab is opt-in per device, so its absence must never degrade a banner."""
        self.assertEqual(degrading_lines((SOURCE / '.claude/hooks/preflight_report.py').read_text()), [])


REPORT_ARGS = ["", "24.0.0", "ready", "ready", "ready", "ready", "ready", "on PATH", "ready"]


def report_rows(root):
    """The preflight report's banner rows for a fixture workspace, every row shown."""
    report = SOURCE / ".claude/hooks/preflight_report.py"
    args = [REPORT_ARGS[0], str(root), *REPORT_ARGS[1:]]
    done = subprocess.run([sys.executable, str(report)] + args, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60, env=dict(os.environ, DEVARNESS_START_ALL="1"))
    if done.returncode:
        raise AssertionError(done.stderr[-400:])
    return [line.strip() for line in json.loads(done.stdout)["systemMessage"].splitlines()]


class DailyCheckBannerTests(unittest.TestCase):
    """The 05:00 dev-check (owner decision 2026-09-24) leaves its verdict in
    .claude/hooks/dev-check-daily/latest.json; a failure must reach the banner."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def banner(self, verdict=None):
        if verdict is not None:
            folder = self.root / ".claude/hooks/dev-check-daily"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "latest.json").write_text(json.dumps(verdict))
        rows = report_rows(self.root)
        daily = [row for row in rows if row.startswith("dev-check daily")]
        degraded = [item for row in rows if row.startswith("Degraded:")
                    for item in row[len("Degraded:"):].split("; ") if "daily dev-check" in item]
        return daily, degraded

    def test_a_device_that_never_ran_it_has_no_row(self):
        self.assertEqual(self.banner(), ([], []))

    def test_a_failed_run_degrades_the_banner_and_names_its_gates(self):
        daily, degraded = self.banner({"finished_at": "2026-09-25T05:00", "exit": 1,
                                       "failed": ["library-tests", "sync-tests"], "log": "2026-09-25.log"})
        self.assertIn("FAILED", daily[0])
        self.assertIn("library-tests, sync-tests", degraded[0])
        self.assertIn("2026-09-25.log", degraded[0])

    def test_a_passed_run_does_not_degrade_it(self):
        daily, degraded = self.banner({"finished_at": "2026-09-25T05:00", "exit": 0, "failed": [],
                                       "log": "2026-09-25.log"})
        self.assertIn("passed", daily[0])
        self.assertEqual(degraded, [])


class TieItUpBannerTests(unittest.TestCase):
    """TieItUp loads Ponytail first; missing files must degrade the start and send agents back to Ponytail."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "Harness").mkdir()
        shutil.copy(SOURCE / "Harness/tieitup-check.py", self.root / "Harness/tieitup-check.py")
        check = runpy.run_path(str(SOURCE / "Harness/tieitup-check.py"))
        for rel in check["REQUIRED"]:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("| ponytail | | |\n| ponytail-review | | |\n")
        (self.root / "CLAUDE.md").write_text(".claude/skills/tieitup/SKILL.md")

    def report(self):
        script = SOURCE / ".claude/hooks/preflight_report.py"
        args = [REPORT_ARGS[0], str(self.root), *REPORT_ARGS[1:]]
        done = subprocess.run([sys.executable, str(script)] + args, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60, env=dict(os.environ, DEVARNESS_START_ALL="1"))
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        out = json.loads(done.stdout)
        rows = [line.strip() for line in out["systemMessage"].splitlines()]
        row = [r for r in rows if r.startswith("tieitup ")]
        degraded = [r for r in rows if r.startswith("Degraded:") and "TieItUp" in r]
        return row, degraded, out["additionalContext"]

    def test_installed_names_tieitup_and_does_not_degrade(self):
        row, degraded, ctx = self.report()
        self.assertEqual(len(row), 1)
        self.assertNotIn("MISSING", row[0])  # the fixture has no Ponytail git clone, so it reads stale
        self.assertEqual(degraded, [])
        self.assertIn(".claude/skills/tieitup/SKILL.md", ctx)
        self.assertIn("tieitup check", ctx)

    def test_a_missing_file_degrades_and_falls_back_to_ponytail(self):
        (self.root / "Harness/bin/tieitup").unlink()
        row, degraded, ctx = self.report()
        self.assertIn("MISSING", row[0])
        self.assertIn("missing Harness/bin/tieitup", degraded[0])
        self.assertIn(".claude/skills/ponytail/SKILL.md", degraded[0])
        self.assertNotIn(".claude/skills/tieitup/SKILL.md", ctx)
        self.assertIn(".claude/skills/ponytail/SKILL.md", ctx)


class LearningLabPlatformTests(unittest.TestCase):
    """learn-claude-code installs only on POSIX; elsewhere it is not applicable.

    Harness/setup-learn-claude.py refuses Windows (upstream imports fcntl) and
    new-device reports the lab "n/a on Windows", so the preflight must not
    call it MISSING there. Each device grades its own platform: nothing here
    fakes os.name, which pathlib reads too.
    """

    PIN = "0" * 40
    LEARN_DEGRADED = "agent learning setup incomplete"

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.write("Harness/repos.txt",
                   "Harness/learn-claude-code\thttps://example.invalid/l.git\t" + self.PIN + "\n")
        for client in (".claude", ".agents"):
            self.write(client + "/skills/task-support/SKILL.md", "---\nname: task-support\n---\n")

    def write(self, relative, body=""):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)

    def banner(self):
        rows = report_rows(self.root)
        learn = [row.split()[1] for row in rows if row.startswith("learn-claude-code ")]
        self.assertEqual(len(learn), 1, rows)
        degraded = " ".join(row for row in rows if row.startswith("Degraded:"))
        return learn[0], degraded

    @unittest.skipUnless(os.name == "nt", "Windows grades its own case")
    def test_an_absent_lab_on_windows_is_not_applicable_and_does_not_degrade(self):
        state, degraded = self.banner()
        self.assertEqual(state, "n/a")
        self.assertNotIn(self.LEARN_DEGRADED, degraded)

    @unittest.skipIf(os.name == "nt", "POSIX grades its own case")
    def test_an_absent_lab_on_posix_is_missing_and_degrades(self):
        state, degraded = self.banner()
        self.assertEqual(state, "MISSING")
        self.assertIn(self.LEARN_DEGRADED, degraded)


if __name__ == "__main__":
    unittest.main()
