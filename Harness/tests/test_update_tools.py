#!/usr/bin/env python3
"""update-tools keeps every device on the pinned tools and advances the pins.

Run: python3 Harness/tests/test_update_tools.py

Every test builds its own upstream as a local bare repository and its own
fake dev, so the suite needs no network, no credentials and no real clone.
"""
import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "Harness" / "bin" / "update-tools"
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t", PYTHONIOENCODING="utf-8")
SAVED = {}
TEST_HOME = None


def setUpModule():
    # The runner's own ~/.config/devarness/personal-repos.txt must not add rows to a fake dev,
    # in this process or in a run_tool child; restored for the next module in a discover run.
    global TEST_HOME
    TEST_HOME = tempfile.TemporaryDirectory(prefix="update-tools-home-")
    home = TEST_HOME.name
    SAVED.update({key: os.environ.get(key) for key in ("HOME", "USERPROFILE")})
    os.environ["HOME"] = os.environ["USERPROFILE"] = home
    ENV.update(HOME=home, USERPROFILE=home)


def tearDownModule():
    for key, value in SAVED.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    TEST_HOME.cleanup()


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=60, env=ENV)


def load():
    loader = importlib.machinery.SourceFileLoader("update_tools", str(TOOL))
    spec = importlib.util.spec_from_loader("update_tools", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class BoundedCleanupTests(unittest.TestCase):
    def test_windows_cleanup_has_its_own_deadline_and_reports_failure(self):
        mod = load()
        for error in (subprocess.TimeoutExpired("taskkill", 5), OSError("taskkill unavailable")):
            with self.subTest(error=type(error).__name__):
                process = mock.Mock(pid=4242)
                process.communicate.side_effect = [subprocess.TimeoutExpired("fixture", 2), ("", "")]
                def taskkill(argv, **options):
                    self.assertLessEqual(options.get("timeout", float("inf")), 5,
                                         "timeout cleanup itself must have a deadline")
                    raise error
                with mock.patch.object(mod.os, "name", "nt"), \
                        mock.patch.object(mod.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
                        mock.patch.object(mod.subprocess, "Popen", return_value=process), \
                        mock.patch.object(mod.subprocess, "run", side_effect=taskkill):
                    result = mod.run_bounded(["fixture"], 2)
                self.assertEqual(result[0], 124)
                self.assertIn("cleanup", result[2])
                process.kill.assert_called_once()

    def test_failed_cleanup_and_open_pipes_still_return_a_timeout(self):
        mod = load()
        process = mock.Mock(pid=4242)
        process.kill.side_effect = OSError("cannot end process")
        process.communicate.side_effect = subprocess.TimeoutExpired("fixture", 2)
        with mock.patch.object(mod.os, "name", "nt"), \
                mock.patch.object(mod.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
                mock.patch.object(mod.subprocess, "Popen", return_value=process), \
                mock.patch.object(mod.subprocess, "run", return_value=types.SimpleNamespace(returncode=1)):
            code, out, err = mod.run_bounded(["fixture"], 2)
        self.assertEqual((code, out), (124, ""))
        self.assertIn("cleanup", err)
        self.assertIn("cannot end process", err)
        self.assertLessEqual(process.communicate.call_args.kwargs["timeout"], 5)


class Fixture:
    """A fake dev with fake upstreams, all on disk."""

    def __init__(self, root: Path):
        self.root = root
        self.dev = root / "dev"
        (self.dev / "Harness" / "bin").mkdir(parents=True)
        (self.dev / ".claude" / "hooks").mkdir(parents=True)
        git("init", "-q", "-b", "main", str(self.dev))
        # update-tools commits in-process, under this process's environment: a test
        # HOME with no git identity (the dev build runs one) must not fail them.
        for key, value in (("user.name", "t"), ("user.email", "t@t")):
            git("config", key, value, cwd=self.dev)
        (self.dev / ".gitignore").write_text("*.state\n.claude/hooks/update-tools/\n", encoding="utf-8")
        self.script("bin/library", "print('catalogue checked')")
        self.upstreams = {}

    def upstream(self, name):
        bare = self.root / (name + ".git")
        git("init", "-q", "--bare", "-b", "main", str(bare))
        work = self.root / (name + "-work")
        git("clone", "-q", str(bare), str(work))
        (work / "README.md").write_text("one\n", encoding="utf-8")
        git("add", "-A", cwd=work)
        git("commit", "-q", "-m", "first", cwd=work)
        git("push", "-q", "origin", "main", cwd=work)
        self.upstreams[name] = (bare, work)
        return bare.as_posix()

    def head(self, name):
        return git("rev-parse", "HEAD", cwd=self.upstreams[name][1]).stdout.strip()

    def push_commit(self, name, subject):
        work = self.upstreams[name][1]
        (work / "README.md").write_text(subject + "\n", encoding="utf-8")
        git("commit", "-qam", subject, cwd=work)
        git("push", "-q", "origin", "main", cwd=work)
        return self.head(name)

    def clone(self, path, name, sha=None):
        full = self.dev / path
        git("clone", "-q", self.upstreams[name][0].as_posix(), str(full))
        git("checkout", "-q", "--detach", sha or self.head(name), cwd=full)
        return full

    def manifest(self, rows):
        """rows: (path, url, sha[, sparse]) tuples; a plain string is a comment line."""
        lines = ["# fake manifest"]
        for row in rows:
            lines.append(row if isinstance(row, str) else "\t".join(row))
        (self.dev / "Harness" / "repos.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        git("add", "-A", cwd=self.dev)
        git("commit", "-q", "-m", "manifest", cwd=self.dev)

    def policy(self, text):
        (self.dev / "Harness" / "updates.txt").write_text(text, encoding="utf-8")

    def script(self, name, body, exit_code=0):
        """A fake installer under Harness/ that logs its arguments and exits as told."""
        path = self.dev / "Harness" / name
        path.write_text("import sys\nopen(%r, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n%s\nsys.exit(%d)\n"
                        % (str(self.dev / "Harness" / (name + ".calls")), body, exit_code), encoding="utf-8")
        return path

    def calls(self, name):
        path = self.dev / "Harness" / (name + ".calls")
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="update-tools-")
        self.fx = Fixture(Path(self.temporary.name).resolve())
        self.mod = load()

    def tearDown(self):
        self.temporary.cleanup()

    def test_the_manifest_reads_three_and_four_field_rows_and_skips_comments(self):
        self.fx.manifest([("Harness/a", "https://x/a.git", "a" * 40), "# note",
                          ("Harness/b", "https://x/b.git", "b" * 40, "docs src")])
        rows = self.mod.read_manifest(self.fx.dev)
        self.assertEqual([(r.path, r.sparse) for r in rows], [("Harness/a", ""), ("Harness/b", "docs src")])

    def personal(self, text):
        path = Path(os.environ["HOME"]) / ".config" / "devarness" / "personal-repos.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.addCleanup(path.unlink)

    def test_the_owners_personal_clones_follow_the_tracked_ones_and_only_report(self):
        # The book PDFs are a third-party repository: their pin lives in
        # ~/.config/devarness, never in git, and update-tools never writes or commits it.
        self.fx.manifest([("Harness/a", "https://x/a.git", "a" * 40)])
        self.fx.policy("Harness/p\tauto\tsetup-p.py --install\t-\n")
        self.personal("# mine\nHarness/p\thttps://x/p.git\t" + "p" * 40 + "\n")
        with mock.patch.dict(os.environ, DEVARNESS_ALLOW_PERSONAL_REPOS="1"):
            rows = self.mod.read_manifest(self.fx.dev)
        self.assertEqual([(r.path, r.personal) for r in rows], [("Harness/a", False), ("Harness/p", True)])
        policy = self.mod.read_policy(self.fx.dev, rows)
        self.assertEqual((policy["Harness/p"].kind, policy["Harness/p"].after), ("report", None))
        self.assertIn("personal-repos.txt", policy["Harness/p"].reason)

    def test_the_policy_table_parses_the_three_kinds_and_dashes(self):
        self.fx.policy("# path\tpolicy\tafter\tcheck\n"
                       "Harness/a\tauto\tsetup-a.py --install\tsetup-a.py --check\n"
                       "Harness/b\thold the lab is pinned\t-\t-\n"
                       "Harness/c\treport Aster releases it\n")
        table = self.mod.read_policy(self.fx.dev)
        self.assertEqual(table["Harness/a"], self.mod.Policy("auto", "", "setup-a.py --install", "setup-a.py --check"))
        self.assertEqual(table["Harness/b"], self.mod.Policy("hold", "the lab is pinned", None, None))
        self.assertEqual(table["Harness/c"], self.mod.Policy("report", "Aster releases it", None, None))

    def test_a_failure_line_loses_its_terminal_colours(self):
        # scholar-sync.sh colours its [fail]; the escapes reached the hold
        # reason and every table that prints it.
        self.assertEqual(self.mod.last_line("ok\n\x1b[1;31m[fail]\x1b[0m Sample Lessons directory not found\n"),
                         "[fail] Sample Lessons directory not found")

    def test_an_unknown_policy_is_refused_with_its_line(self):
        self.fx.policy("Harness/a\tmaybe\t-\t-\n")
        with self.assertRaises(SystemExit) as caught:
            self.mod.read_policy(self.fx.dev)
        self.assertIn("updates.txt:1", str(caught.exception))

    def test_a_missing_policy_table_means_everything_is_auto(self):
        self.assertEqual(self.mod.read_policy(self.fx.dev), {})

    def test_a_scan_that_reaches_too_few_upstreams_counts_for_nothing(self):
        # M2: an offline start spent the day's floor and emptied the behind
        # list. A scan under 80% now leaves last_scan alone, and each upstream
        # it did not reach keeps the head the last scan saw.
        state = {"heads": {"u1": "a" * 40, "u2": "b" * 40}, "last_scan": 100.0}
        self.mod.record_scan(state, {"u1": None, "u2": None, "u3": "c" * 40}, whole=True)
        self.assertEqual(state["last_scan"], 100.0)
        self.assertEqual(state["heads"], {"u1": "a" * 40, "u2": "b" * 40, "u3": "c" * 40})
        self.assertEqual((state["scan"]["reached"], state["scan"]["total"]), (1, 3))
        self.mod.record_scan(state, {"u1": "d" * 40, "u2": "b" * 40, "u3": "c" * 40}, whole=True)
        self.assertGreater(state["last_scan"], 100.0)
        self.assertEqual(state["heads"]["u1"], "d" * 40)

    def test_a_run_on_a_few_rows_keeps_their_heads_but_is_not_the_scan(self):
        state = {}
        self.mod.record_scan(state, {"u1": "a" * 40}, whole=False)
        self.assertEqual(state, {"heads": {"u1": "a" * 40}})

    def test_the_plugin_step_is_due_once_a_day(self):
        hour_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        day_ago = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 25 * 3600))
        self.assertFalse(self.mod.plugins_due({"last_plugins": {"at": hour_ago}}, force=False))
        self.assertTrue(self.mod.plugins_due({"last_plugins": {"at": hour_ago}}, force=True))
        self.assertTrue(self.mod.plugins_due({"last_plugins": {"at": day_ago}}, force=False))
        self.assertTrue(self.mod.plugins_due({}, force=False))

    def test_a_daily_run_a_little_earlier_than_yesterdays_still_runs_plugins(self):
        # The step stamps when it ends and the next 04:00 run checks before that
        # time of day, so a 24 h floor skipped every other day (Task 1 review).
        def ago(hours):
            return {"last_plugins": {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                        time.gmtime(time.time() - hours * 3600))}}
        self.assertTrue(self.mod.plugins_due(ago(23), force=False))
        self.assertFalse(self.mod.plugins_due(ago(19), force=False))

    def test_reapply_writes_this_devices_moves_and_keeps_origins(self):
        base = "# c\nHarness/a\tU\t1\nHarness/b\tV\t1\nHarness/c\tW\t1\n"
        ours = "# c\nHarness/a\tU\t2\nHarness/b\tV\t2\nHarness/c\tW\t1\n"
        remote = "# c\nHarness/a\tU\t1\nHarness/b\tV\t3\nHarness/c\tW\t4\n# a comment origin added\n"
        self.assertEqual(self.mod.reapply_pins(remote, base, ours),
                         "# c\nHarness/a\tU\t2\nHarness/b\tV\t3\nHarness/c\tW\t4\n# a comment origin added\n")


class RealTableTests(unittest.TestCase):
    """The tracked updates.txt must agree with repos.txt and name real installers."""

    def setUp(self):
        self.mod = load()

    def test_every_per_device_file_is_ignored(self):
        # Per-device lock and runtime state must never be versioned.
        for rel in (self.mod.STATE, self.mod.LOCK, self.mod.LOGS + "/x.log",
                    "Harness/docling.partial/HEAD", "Harness/pcb/Konnect.partial/HEAD"):
            self.assertEqual(subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT).returncode, 0, rel)

    def test_the_daily_task_is_the_long_run_the_banner_asks_for_before_dev_check(self):
        # Installers and the plugin step require the scheduled long run.
        import xml.etree.ElementTree as ET
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        options = dict(self.mod.DAILY_TASK)
        options.pop("task")
        xml = self.mod.load_dev_check().daily_task_xml("pythonw.exe", "C:/fixture-workspace/Harness/bin/update-tools", "FIXTURE-PC\\example", **options)
        root = ET.fromstring(xml.split("\n", 1)[1])
        arguments = root.find("t:Actions/t:Exec/t:Arguments", ns).text
        self.assertEqual("update-tools " + arguments.split('" ', 1)[1], self.mod.LONG_RUN)
        start = root.find("t:Triggers/t:CalendarTrigger/t:StartBoundary", ns).text
        self.assertLess(start[11:], "05:00:00")             # done before dev-check's 05:00

    def test_every_policy_row_names_a_manifest_path(self):
        paths = {r.path for r in self.mod.read_manifest(ROOT)}
        for path in self.mod.read_policy(ROOT):
            self.assertIn(path, paths, path)

    def test_every_after_and_check_command_names_a_file_that_exists(self):
        for path, policy in self.mod.read_policy(ROOT).items():
            for command in (policy.after, policy.check):
                if command:
                    first = command.split()[0]
                    if first.endswith(".py") or first.endswith(".sh") or first.startswith("bin/"):
                        self.assertTrue((ROOT / "Harness" / first).is_file(), "%s names %s" % (path, first))

    def test_the_pcb_clones_only_report(self):
        table = self.mod.read_policy(ROOT)
        for path, policy in table.items():
            if path.startswith("PCB Tools/"):
                self.assertEqual(policy.kind, "report", path)


class DailyRunTests(unittest.TestCase):
    """The daily long run on each system; no real task or agent is registered."""

    def setUp(self):
        self.mod = load()
        self.temporary = tempfile.TemporaryDirectory(prefix="update-tools-home-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.calls = []

    def run_fake(self, argv):
        self.calls.append(argv)
        return 0

    def test_on_macos_install_daily_goes_through_dev_check_s_scheduler(self):
        # The shared scheduler owns both daily jobs. A second writer could leave
        # launch and new-device callers looking for different job labels.
        calls = []
        scheduler = types.SimpleNamespace(schedule=lambda install, **task: calls.append((install, task)) or 0)
        with mock.patch.object(self.mod.platform, "system", return_value="Darwin"), \
                mock.patch.object(self.mod, "load_dev_check", return_value=scheduler), \
                mock.patch.object(self.mod, "launch_agent", create=True, side_effect=AssertionError("a second writer")):
            self.assertEqual(self.mod.install_daily(True, ROOT), 0)
        self.assertEqual((calls[0][0], calls[0][1]["task"], calls[0][1]["hour"]), (True, "DEVARNESS_update_daily", 4))
        self.assertEqual(self.mod.agent_path(self.home), self.home / "Harness" / "LaunchAgents" / "DEVARNESS_update_daily.plist")

    def test_portable_bootstrap_leaves_daily_setup_explicit(self):
        # Default onboarding reports the core without writing launchers or tasks.
        marker = self.home / "existing-profile"
        marker.write_text("unchanged", encoding="utf-8")
        done = subprocess.run([sys.executable, str(ROOT / "tools/bootstrap.py"), "--json"],
                              capture_output=True, text=True, timeout=20,
                              env=dict(ENV, HOME=str(self.home), USERPROFILE=str(self.home)))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(json.loads(done.stdout)["core_ready"])
        self.assertEqual(list(self.home.iterdir()), [marker])
        self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")


class LaunchTests(unittest.TestCase):
    """A start hands long work to a background run. run and spawn are fakes,
    so no real task, agent or process is ever started here."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="update-tools-")
        self.addCleanup(self.temporary.cleanup)
        self.fx = Fixture(Path(self.temporary.name).resolve())
        self.mod = load()
        self.calls, self.spawned = [], []

    def run_fake(self, argv):
        self.calls.append(argv)
        return 0

    def spawn_fake(self, root):
        self.spawned.append(root)

    def state(self, *results):
        return {"last_run": {"at": "2026-09-25T09:00:00Z", "seconds": 1.0,
                             "results": [{"what": w, "state": s, "note": ""} for w, s in results]}}

    def launch(self, state, system):
        return self.mod.launch(self.fx.dev, state, system=system, home=self.fx.root,
                               run=self.run_fake, spawn=self.spawn_fake)

    def test_long_work_on_windows_starts_the_registered_task(self):
        state = self.state(("Harness/docling", "absent"), ("Harness/laya", "pending"),
                           ("plugins", "pending"), ("Harness/herdr", "advanced"))
        line = self.launch(state, "Windows")
        self.assertEqual(self.calls, [["schtasks", "/Run", "/TN", "DEVARNESS_update_daily"]])
        self.assertEqual(self.spawned, [])
        self.assertEqual(line, "updates: background run started (DEVARNESS_update_daily) for docling, laya, plugins")
        self.assertEqual(state["launched"]["for"], ["docling", "laya", "plugins"])

    def test_nothing_waiting_starts_nothing(self):
        line = self.launch(self.state(("Harness/herdr", "advanced"), ("upstreams", "scanned")), "Windows")
        self.assertEqual((line, self.calls, self.spawned), ("", [], []))

    def test_a_mac_kicks_its_agent_or_starts_a_process_when_it_has_none(self):
        line = self.launch(self.state(("Harness/laya", "deferred")), "Darwin")
        self.assertEqual((self.calls, len(self.spawned)), ([], 1))
        self.assertIn("install-daily", line)
        self.mod.agent_path(self.fx.root).parent.mkdir(parents=True)
        self.mod.agent_path(self.fx.root).write_bytes(b"<plist/>")
        self.launch(self.state(("Harness/laya", "deferred")), "Darwin")
        self.assertEqual(self.calls[-1][:2], ["launchctl", "kickstart"])
        self.assertTrue(self.calls[-1][2].endswith("/DEVARNESS_update_daily"))

    def test_a_running_long_run_is_not_started_twice(self):
        # Review Focus 4: the 04:00 task, or the last start's launch, holds the lock.
        lock = self.fx.dev / ".claude" / "hooks" / "update-tools.lock"
        lock.write_text("pid %d since now\n" % os.getpid(), encoding="utf-8")
        line = self.launch(self.state(("Harness/docling", "absent")), "Windows")
        self.assertEqual((line, self.calls, self.spawned), ("", [], []))
        # The start banner reports a run that is currently in progress.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.mod.main(["--root", str(self.fx.dev), "banner"])
        self.assertIn("updates: a run is running now (pid %d since now); its result follows it" % os.getpid(),
                      out.getvalue())

    def test_the_launch_command_with_nothing_waiting_is_silent(self):
        # A fresh device's state is empty, so this starts nothing real; and it
        # runs in-process with fakes that fail the test if a real start is ever
        # tried, since Windows finds schtasks whatever PATH says (final review).
        self.assertFalse((self.fx.dev / ".claude" / "hooks" / "update-tools.state").exists())

        def real_start(*args, **kwargs):
            raise AssertionError("the launch command tried to start a real run")
        self.mod.run_quiet = self.mod.spawn_detached = real_start
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = self.mod.main(["--root", str(self.fx.dev), "launch"])
        self.assertEqual((rc, out.getvalue()), (0, ""))

    def test_a_clone_left_to_its_own_command_launches_nothing(self):
        # Every run skips a clone that ran out of a
        # whole run until `update-tools apply --only` names it or its pin moves,
        # so a launch for it would only spend a run.
        state = self.state(("Harness/docling", "absent"), ("Harness/laya", "absent"))
        state["clone_timeouts"] = {"Harness/docling": {"at": "2026-09-26T01:00:00Z", "sha": "a" * 40}}
        self.assertEqual(self.mod.queued(state), ["laya"])
        state["last_run"]["results"].pop()
        self.assertEqual((self.launch(state, "Windows"), self.calls, self.spawned), ("", [], []))

    @unittest.skipUnless(os.name == "nt", "CREATE_NO_WINDOW is Windows'")
    def test_a_windowless_run_opens_no_console_for_its_git_calls(self):
        # Detached children of windowless processes must also suppress console
        # windows so a scheduled background run does not open visible terminals.
        flags = []

        def popen(argv, **options):
            flags.append(options.get("creationflags", 0))
            raise OSError("recorded, never started")
        with mock.patch.object(self.mod.subprocess, "Popen", side_effect=popen):
            self.mod.run_bounded(["git", "--version"], 5)
        self.assertTrue(flags[0] & subprocess.CREATE_NO_WINDOW)

    @unittest.skipUnless(os.name == "nt", "CREATE_NO_WINDOW is Windows'")
    def test_ending_a_timed_out_tree_opens_no_console_either(self):
        # kill_tree's taskkill runs at each timeout
        # and would open a window in a windowless run, as run_bounded's calls did.
        calls = []

        def run(argv, **options):
            calls.append((argv[0], options.get("creationflags", 0)))
            return types.SimpleNamespace(returncode=0)
        with mock.patch.object(self.mod.subprocess, "run", side_effect=run):
            self.mod.kill_tree(mock.Mock(pid=4242))       # a stand-in: nothing is ended
        self.assertEqual(calls[0][0], "taskkill")
        self.assertTrue(calls[0][1] & subprocess.CREATE_NO_WINDOW)

    @unittest.skipUnless(os.name == "nt", "pythonw is Windows'")
    def test_an_installer_runs_under_the_console_python_not_pythonw(self):
        # 2026-09-28: CREATE_NO_WINDOW is ignored for pythonw, which has no
        # console, so setup-deerflow.py under pythonw opened a visible cmd
        # window for pnpm. The console python gets a hidden one its children share.
        root = Path(tempfile.mkdtemp())
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        with mock.patch.object(self.mod.sys, "executable", str(pythonw)):
            argv = self.mod.command_argv(root, "setup-deerflow.py --install")
        self.assertEqual(Path(argv[0]).name.lower(), "python.exe")

    def launched(self, state, hours_ago, work):
        """state as a launch for work left it, hours_ago hours ago."""
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - hours_ago * 3600))
        state["launched"] = {"at": at, "how": "DEVARNESS_update_daily", "for": work}
        return state

    def test_the_same_queue_is_not_launched_again_within_six_hours(self):
        # Work a long run cannot finish, a folder
        # in a clone's way say, would otherwise launch a run at every start.
        for system in ("Windows", "Darwin"):          # the task's run, or a detached spawn
            with self.subTest(system=system):
                self.calls, self.spawned = [], []
                state = self.launched(self.state(("Harness/docling", "absent")), 1, ["docling"])
                self.assertEqual((self.launch(state, system), self.calls, self.spawned), ("", [], []))

    def test_a_different_queue_launches_at_once(self):
        state = self.launched(self.state(("Harness/docling", "absent"), ("Harness/laya", "pending")), 1, ["docling"])
        self.assertIn("for docling, laya", self.launch(state, "Windows"))
        self.assertEqual(self.calls, [["schtasks", "/Run", "/TN", "DEVARNESS_update_daily"]])

    def test_the_same_queue_launches_again_after_six_hours(self):
        state = self.launched(self.state(("Harness/docling", "absent")), 7, ["docling"])
        self.assertIn("for docling", self.launch(state, "Windows"))
        self.assertEqual(self.calls, [["schtasks", "/Run", "/TN", "DEVARNESS_update_daily"]])


class FollowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="update-tools-")
        self.fx = Fixture(Path(self.temporary.name).resolve())
        self.mod = load()
        self.logs = self.fx.dev / ".claude" / "hooks" / "update-tools"

    def tearDown(self):
        self.temporary.cleanup()

    def follow(self, budget=600, state=None):
        rows = self.mod.read_manifest(self.fx.dev)
        policy = self.mod.read_policy(self.fx.dev)
        return self.mod.follow_pins(self.fx.dev, rows, policy, time.monotonic() + budget, self.logs,
                                    state if state is not None else {})

    def test_a_follow_with_an_installer_waits_for_a_long_run(self):
        # An installer can take minutes; a start with 60 s must not move the
        # clone and leave the tool without its runtime. The clone stays at the
        # old pin, working, until a run with time.
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        clone = self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, new)])
        self.fx.script("setup-a.py", "")
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        results = self.follow(budget=60)
        self.assertEqual(results[0].state, "deferred", results)
        self.assertIn("long run", results[0].note)
        self.assertEqual(git("rev-parse", "HEAD", cwd=clone).stdout.strip(), old)
        self.assertEqual(self.fx.calls("setup-a.py"), [])

    def test_a_stuck_tool_is_retried_at_every_run_until_its_installer_passes(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, new)])
        flag = self.fx.dev / "Harness" / "fixed.flag"
        self.fx.script("setup-a.py", "import os\nsys.exit(0 if os.path.exists(%r) else 3)" % str(flag))
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        state = {}
        self.assertEqual(self.follow(state=state)[0].state, "stuck")
        self.assertIn("Harness/a", state["stuck"])
        self.assertEqual(self.follow(state=state)[0].state, "stuck")     # still reported, still tried
        flag.write_text("fixed\n", encoding="utf-8")
        self.assertEqual(self.follow(state=state)[0].state, "followed")
        self.assertNotIn("Harness/a", state["stuck"])
        self.assertEqual(len(self.fx.calls("setup-a.py")), 3)

    def test_a_follow_marks_the_tool_stuck_on_disk_while_its_installer_runs(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, new)])
        state_file = self.fx.dev / ".claude" / "hooks" / "update-tools.state"
        self.fx.script("setup-a.py", "import json\nsys.exit(0 if 'Harness/a' in json.load(open(%r)).get('stuck', {}) else 5)"
                       % str(state_file))
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        state = {}
        self.assertEqual(self.follow(state=state)[0].state, "followed")
        self.assertNotIn("Harness/a", state["stuck"])

    def test_a_clone_behind_its_pin_is_moved_without_the_network(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        clone = self.fx.clone("Harness/a", "a", old)
        git("fetch", "-q", "origin", cwd=clone)      # the commit is present locally
        git("remote", "set-url", "origin", "https://127.0.0.1:9/none.git", cwd=clone)
        self.fx.manifest([("Harness/a", url, new)])
        results = self.follow()
        self.assertEqual(results[0].state, "followed", results)
        self.assertEqual(git("rev-parse", "HEAD", cwd=clone).stdout.strip(), new)

    def test_a_clone_at_its_pin_is_left_alone_and_unreported(self):
        url = self.fx.upstream("a")
        self.fx.clone("Harness/a", "a")
        self.fx.manifest([("Harness/a", url, self.fx.head("a"))])
        self.assertEqual(self.follow(), [])

    def test_a_long_run_clones_a_missing_row_partially_at_its_pin(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.push_commit("a", "second")
        self.fx.manifest([("Harness/a", url, old)])
        results = self.follow(budget=600)
        self.assertEqual([(r.what, r.state) for r in results], [("Harness/a", "cloned")], results)
        clone = self.fx.dev / "Harness" / "a"
        self.assertEqual(git("rev-parse", "HEAD", cwd=clone).stdout.strip(), old)
        self.assertEqual(git("config", "--get", "remote.origin.partialclonefilter", cwd=clone).stdout.strip(),
                         "blob:none")
        self.assertFalse((self.fx.dev / "Harness" / "a.partial").exists())

    def test_a_start_leaves_a_missing_clone_to_the_background_run(self):
        url = self.fx.upstream("a")
        self.fx.manifest([("Harness/a", url, self.fx.head("a"))])
        results = self.follow(budget=60)
        self.assertEqual(results[0].state, "absent")
        self.assertIn("background run", results[0].note)
        self.assertFalse((self.fx.dev / "Harness" / "a").exists())

    def test_a_failed_clone_leaves_nothing_at_the_path(self):
        self.fx.manifest([("Harness/a", "https://127.0.0.1:9/none.git", "a" * 40)])
        results = self.follow(budget=600)
        self.assertEqual(results[0].state, "absent", results)
        self.assertTrue(results[0].note.startswith("clone:"), results)
        self.assertFalse((self.fx.dev / "Harness" / "a").exists())
        self.assertFalse((self.fx.dev / "Harness" / "a.partial").exists())

    def test_a_missing_sparse_row_checks_out_only_its_directories(self):
        url = self.fx.upstream("a")
        work = self.fx.upstreams["a"][1]
        for folder in ("book", "data"):
            (work / folder).mkdir()
            (work / folder / "x.md").write_text(folder + "\n", encoding="utf-8")
        git("add", "-A", cwd=work)
        git("commit", "-qm", "two folders", cwd=work)
        git("push", "-q", "origin", "main", cwd=work)
        self.fx.manifest([("Harness/a", url, self.fx.head("a"), "book")])
        results = self.follow(budget=600)
        self.assertEqual(results[0].state, "cloned", results)
        self.assertTrue((self.fx.dev / "Harness" / "a" / "book" / "x.md").is_file())
        self.assertFalse((self.fx.dev / "Harness" / "a" / "data").exists())

    def test_a_half_made_clone_is_never_read_as_dev_itself(self):
        # Review Focus 1: git run in an empty .git inside dev answers with dev's
        # own HEAD, and every later call would act on dev (verified 2026-09-25).
        url = self.fx.upstream("a")
        self.fx.manifest([("Harness/a", url, self.fx.head("a"))])
        (self.fx.dev / "Harness" / "a" / ".git").mkdir(parents=True)
        row = self.mod.read_manifest(self.fx.dev)[0]
        self.assertIsNone(self.mod.clone_head(self.fx.dev, row))
        results = self.follow(budget=600)
        self.assertEqual(results[0].state, "absent", results)
        self.assertIn("not a clone", results[0].note)
        self.assertEqual([p.name for p in (self.fx.dev / "Harness" / "a").iterdir()], [".git"])

    def test_a_locked_partial_ends_only_its_row(self):
        # C1: on Windows a file held open under a leftover .partial, by a virus
        # scanner say, makes its removal raise (WinError 32). Only that row is
        # absent, with the reason; the run goes on to the next row.
        url = self.fx.upstream("a")
        sha = self.fx.head("a")
        self.fx.manifest([("Harness/a", url, sha), ("Harness/b", url, sha)])
        locked = self.fx.dev / "Harness" / "a.partial"
        locked.mkdir()
        rmtree = self.mod.shutil.rmtree

        def held_open(path, *args, **kwargs):
            if Path(path) == locked:
                raise PermissionError(13, "held open by another program", str(path))
            return rmtree(path, *args, **kwargs)

        self.mod.shutil.rmtree = held_open      # the process's one shutil: restored below
        try:
            results = self.follow(budget=600)
        except OSError as exc:
            self.fail("one locked folder ended the whole run: %r" % exc)
        finally:
            self.mod.shutil.rmtree = rmtree
        self.assertEqual([(r.what, r.state) for r in results], [("Harness/a", "absent"), ("Harness/b", "cloned")], results)
        self.assertIn("Harness/a.partial could not be removed", results[0].note)

    def test_a_clone_that_cannot_be_moved_into_place_ends_only_its_row(self):
        # Windows refuses to rename a folder while a file inside is held open,
        # and a fresh clone is what a virus scanner reads. Only that row is
        # absent; its .partial stays for the next long run, and the run goes on.
        url = self.fx.upstream("a")
        sha = self.fx.head("a")
        self.fx.manifest([("Harness/a", url, sha), ("Harness/b", url, sha)])
        partial = self.fx.dev / "Harness" / "a.partial"
        replace = self.mod.os.replace

        def held_open(source, *args, **kwargs):
            if Path(source) == partial:
                raise PermissionError(13, "held open by another program", str(source))
            return replace(source, *args, **kwargs)

        self.mod.os.replace = held_open         # the process's one os: restored below
        try:
            results = self.follow(budget=600)
        except OSError as exc:
            self.fail("one clone that would not move ended the whole run: %r" % exc)
        finally:
            self.mod.os.replace = replace
        self.assertEqual([(r.what, r.state) for r in results], [("Harness/a", "absent"), ("Harness/b", "cloned")], results)
        self.assertIn("Harness/a.partial could not be moved into place", results[0].note)
        self.assertTrue((partial / ".git").is_dir(), "the clone in Harness/a.partial was deleted")

    def test_a_row_that_timed_out_is_skipped_at_the_next_run(self):
        # The book PDFs' clone is about 3 GB: on a slow link each long run would
        # download it again and time out again, for ever.
        url = self.fx.upstream("a")
        sha = self.fx.head("a")
        self.fx.manifest([("Harness/a", url, sha)])
        state = {"clone_timeouts": {"Harness/a": {"at": "2026-09-26T01:00:00Z", "sha": sha}}}
        results = self.follow(budget=600, state=state)
        self.assertEqual([(r.what, r.state) for r in results], [("Harness/a", "absent")], results)
        self.assertEqual(results[0].note,
                         "did not finish in one run; update-tools apply --only Harness/a --budget 6000 gives it the time")
        self.assertFalse((self.fx.dev / "Harness" / "a").exists())
        self.assertFalse((self.fx.dev / "Harness" / "a.partial").exists())

    def test_a_new_pin_clears_a_timed_out_row(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        self.fx.manifest([("Harness/a", url, new)])
        state = {"clone_timeouts": {"Harness/a": {"at": "2026-09-26T01:00:00Z", "sha": old}}}
        results = self.follow(budget=600, state=state)
        self.assertEqual([(r.what, r.state) for r in results], [("Harness/a", "cloned")], results)
        self.assertNotIn("Harness/a", state["clone_timeouts"])

    def test_a_timeout_on_a_short_share_leaves_no_record(self):
        # A clone that starts late in a run, after an installer or another
        # clone used most of it, gets a whole share at the next long run.
        url = self.fx.upstream("a")
        self.fx.manifest([("Harness/a", url, self.fx.head("a"))])
        self.mod.git = lambda repo, *args, timeout=0: (124, "", "timed out after %ss" % timeout)
        state = {}
        results = self.follow(budget=600, state=state)          # a share of 280 s
        self.assertEqual(results[0].note, "out of time; the next long run clones it", results)
        self.assertEqual(state["clone_timeouts"], {})

    def test_the_post_update_command_runs_after_a_follow(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, new)])
        self.fx.script("setup-a.py", "")
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        self.assertEqual(self.follow()[0].state, "followed")
        self.assertEqual(self.fx.calls("setup-a.py"), ["--install"])

    def test_a_failed_post_update_command_leaves_the_tool_stuck_and_named(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, new)])
        self.fx.script("setup-a.py", "print('no runtime')", exit_code=2)
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        result = self.follow()[0]
        self.assertEqual(result.state, "stuck")
        self.assertIn("setup-a.py", result.note)
        self.assertIn("no runtime", (self.logs / "a.log").read_text(encoding="utf-8"))

    def test_a_clone_with_local_changes_is_never_forced(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        clone = self.fx.clone("Harness/a", "a", old)
        (clone / "README.md").write_text("edited by hand\n", encoding="utf-8")
        self.fx.manifest([("Harness/a", url, new)])
        result = self.follow()[0]
        self.assertEqual(result.state, "stuck")
        self.assertIn("local changes", result.note)
        self.assertEqual((clone / "README.md").read_text(encoding="utf-8"), "edited by hand\n")

    def test_out_of_time_defers_the_rest(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, new)])
        results = self.follow(budget=-1)
        self.assertEqual(results[0].state, "deferred")

    def test_a_move_is_never_started_inside_the_checkout_margin(self):
        # session_start kills the tree at budget + 5 s; a checkout cut there
        # leaves a half-written clone that reads as a hand edit for ever.
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        clone = self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, new)])
        results = self.follow(budget=self.mod.MOVE_MARGIN - 5)
        self.assertEqual(results[0].state, "deferred", results)
        self.assertEqual(git("rev-parse", "HEAD", cwd=clone).stdout.strip(), old)

    def test_a_dirty_clone_already_at_the_target_needs_no_checkout(self):
        url = self.fx.upstream("a")
        sha = self.fx.head("a")
        clone = self.fx.clone("Harness/a", "a", sha)
        (clone / "README.md").write_text("edited by hand\n", encoding="utf-8")
        row = self.mod.Row("Harness/a", url, sha, "")
        self.assertEqual(self.mod.checkout(self.fx.dev, row, sha, self.logs / "a.log"), (True, ""))

    def test_a_shell_after_command_runs_under_git_bash_not_wsl(self):
        # On Windows a bare "bash" given to subprocess is System32's, WSL's,
        # which runs nothing of ours; the launcher must find Git Bash itself.
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        new = self.fx.push_commit("a", "second")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, new)])
        marker = self.fx.dev / "Harness" / "after.calls"
        (self.fx.dev / "Harness" / "after.sh").write_text(
            "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >> \"$(dirname \"$0\")/after.calls\"\n", encoding="utf-8")
        self.fx.policy("Harness/a\tauto\tafter.sh --install\t-\n")
        self.assertEqual(self.follow()[0].state, "followed")
        self.assertEqual(marker.read_text(encoding="utf-8"), "--install\n")


class AdvanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="update-tools-")
        self.fx = Fixture(Path(self.temporary.name).resolve())
        self.mod = load()
        self.logs = self.fx.dev / ".claude" / "hooks" / "update-tools"
        self.state = {}

    def tearDown(self):
        self.temporary.cleanup()

    def advance(self, budget=600):
        rows = self.mod.read_manifest(self.fx.dev)
        policy = self.mod.read_policy(self.fx.dev, rows)
        heads = self.mod.scan_upstreams(sorted({r.url for r in rows}), 30)
        return self.mod.advance(self.fx.dev, rows, policy, heads, self.state,
                                time.monotonic() + budget, self.logs)

    def test_an_absent_clone_is_skipped_in_phase_two(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.manifest([("Harness/a", url, old)])      # bootstrap has not made the clone
        self.fx.push_commit("a", "second")
        results, moves = self.advance()
        self.assertEqual(results[0].state, "absent", results)
        self.assertEqual(moves, [])
        self.assertEqual(self.state.get("held", {}), {})

    def test_a_tool_with_an_installer_waits_for_a_long_run_in_phase_two(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        self.fx.script("setup-a.py", "")
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        self.fx.push_commit("a", "second")
        results, moves = self.advance(budget=60)
        self.assertEqual(results[0].state, "pending", results)
        self.assertIn("long run", results[0].note)
        self.assertEqual(moves, [])
        self.assertIn("Harness/a\t%s\t%s\n" % (url, old), self.manifest_text())
        self.assertEqual(self.fx.calls("setup-a.py"), [])

    def manifest_text(self):
        return (self.fx.dev / "Harness" / "repos.txt").read_text(encoding="utf-8")

    def test_the_scan_answers_every_url_and_none_for_an_unreachable_one(self):
        url = self.fx.upstream("a")
        heads = self.mod.scan_upstreams([url, "https://127.0.0.1:9/none.git"], 30)
        self.assertEqual(heads[url], self.fx.head("a"))
        self.assertIsNone(heads["https://127.0.0.1:9/none.git"])

    def test_a_newer_upstream_moves_the_clone_and_the_manifest(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        new = self.fx.push_commit("a", "second")
        results, moves = self.advance()
        self.assertEqual(results[0].state, "advanced", results)
        self.assertEqual(moves, [("Harness/a", old, new)])
        self.assertIn("Harness/a\t%s\t%s\n" % (url, new), self.manifest_text())

    def test_a_personal_clone_whose_upstream_moved_is_reported_and_never_moved(self):
        url = self.fx.upstream("p")
        old = self.fx.head("p")
        self.fx.clone("Harness/p", "p", old)
        self.fx.manifest([])
        personal = Path(os.environ["HOME"]) / ".config" / "devarness" / "personal-repos.txt"
        personal.parent.mkdir(parents=True, exist_ok=True)
        personal.write_text("Harness/p\t%s\t%s\n" % (url, old), encoding="utf-8")
        self.addCleanup(personal.unlink)
        new = self.fx.push_commit("p", "second")
        with mock.patch.dict(os.environ, DEVARNESS_ALLOW_PERSONAL_REPOS="1"):
            results, moves = self.advance()
        self.assertEqual((results[0].state, moves), ("report", []), results)
        self.assertIn(new[:7], results[0].note)
        self.assertEqual(personal.read_text(encoding="utf-8"), "Harness/p\t%s\t%s\n" % (url, old))
        self.assertNotIn(url, self.manifest_text())
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev / "Harness" / "p").stdout.strip(), old)

    def test_two_rows_with_one_upstream_move_together_and_comments_survive(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/one", "a", old)
        self.fx.clone("Harness/two", "a", old)
        self.fx.manifest([("Harness/one", url, old), "# the same upstream twice, on purpose",
                          ("Harness/two", url, old, "docs")])
        new = self.fx.push_commit("a", "second")
        results, moves = self.advance()
        self.assertEqual(len(moves), 1)
        text = self.manifest_text()
        self.assertIn("# the same upstream twice, on purpose\n", text)
        self.assertIn("Harness/two\t%s\t%s\tdocs\n" % (url, new), text)
        self.assertNotIn("\r", text)
        for path in ("Harness/one", "Harness/two"):
            self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev / path).stdout.strip(), new)

    def test_a_failing_installer_rolls_back_restores_the_runtime_and_holds(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        self.fx.script("setup-a.py", "import os\nsys.exit(2 if 'second' in open(os.path.join(%r, 'README.md')).read() else 0)"
                       % str(self.fx.dev / "Harness" / "a"))
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        new = self.fx.push_commit("a", "second")
        results, moves = self.advance()
        self.assertEqual(results[0].state, "rolled back", results)
        self.assertIn("setup-a.py", results[0].note)
        self.assertEqual(moves, [])
        self.assertIn("Harness/a\t%s\t%s\n" % (url, old), self.manifest_text())
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev / "Harness" / "a").stdout.strip(), old)
        self.assertEqual(self.fx.calls("setup-a.py"), ["--install", "--install"])   # once at new, once to restore
        self.assertEqual(self.state["held"]["Harness/a"]["at"], new)

    def test_a_failed_restore_leaves_the_tool_stuck_for_the_next_run(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        self.fx.script("setup-a.py", "", exit_code=2)       # fails at both pins
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        self.fx.push_commit("a", "second")
        results, _ = self.advance()
        self.assertEqual(results[0].state, "rollback failed", results)
        self.assertEqual(self.state["stuck"]["Harness/a"]["at"], old)
        rows = self.mod.read_manifest(self.fx.dev)
        again = self.mod.follow_pins(self.fx.dev, rows, self.mod.read_policy(self.fx.dev),
                                     time.monotonic() + 600, self.logs, self.state)
        self.assertEqual(again[0].state, "stuck", again)

    def test_a_move_is_left_pending_inside_the_checkout_margin(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        self.fx.push_commit("a", "second")
        results, moves = self.advance(budget=self.mod.MOVE_MARGIN - 5)
        self.assertEqual(results[0].state, "pending", results)
        self.assertEqual(moves, [])

    def test_an_installer_that_never_finishes_leaves_the_tool_stuck(self):
        # A run killed mid-installer left a half-built runtime at the new pin
        # silently without an explicit marker: the tool is marked stuck
        # on disk before its installer starts, and cleared when it passes.
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        state_file = self.fx.dev / ".claude" / "hooks" / "update-tools.state"
        self.fx.script("setup-a.py", "import json\nsys.exit(0 if 'Harness/a' in json.load(open(%r)).get('stuck', {}) else 5)"
                       % str(state_file))
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        self.fx.push_commit("a", "second")
        results, _ = self.advance()
        self.assertEqual(results[0].state, "advanced", results)
        self.assertNotIn("Harness/a", self.state.get("stuck", {}))

    def test_a_failed_fetch_is_tried_again_at_the_next_run(self):
        # A network blip is not a broken upstream: holding the tool until
        # upstream moves again would strand it.
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        clone = self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        new = self.fx.push_commit("a", "second")
        git("remote", "set-url", "origin", "https://127.0.0.1:9/none.git", cwd=clone)
        results, _ = self.advance()
        self.assertIn("fetch", results[0].note, results)
        git("remote", "set-url", "origin", url, cwd=clone)
        results, moves = self.advance()
        self.assertEqual(results[0].state, "advanced", results)
        self.assertEqual(moves[0][2], new)

    def test_a_failing_check_rolls_back_too(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        self.fx.script("check-a.py", "", exit_code=1)
        self.fx.policy("Harness/a\tauto\t-\tcheck-a.py\n")
        self.fx.push_commit("a", "second")
        results, _ = self.advance()
        self.assertEqual(results[0].state, "rolled back")
        self.assertIn("check", results[0].note)

    def test_a_held_upstream_commit_is_skipped_and_a_newer_one_is_tried(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        new = self.fx.push_commit("a", "second")
        self.state = {"held": {"Harness/a": {"at": new, "reason": "broke", "when": "t"}}}
        results, moves = self.advance()
        self.assertEqual(results[0].state, "held")
        self.assertEqual(moves, [])
        newer = self.fx.push_commit("a", "third")
        results, moves = self.advance()
        self.assertEqual(results[0].state, "advanced")
        self.assertEqual(moves[0][2], newer)

    def test_a_held_tool_with_an_installer_reads_held_at_a_start_and_queues_no_launch(self):
        # Read the hold before estimating installer time so a held tool does
        # not launch a redundant long run.
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        self.fx.script("setup-a.py", "")
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        new = self.fx.push_commit("a", "second")
        self.state = {"held": {"Harness/a": {"at": new, "reason": "check failed", "when": "t", "timeout": 900}}}
        results, moves = self.advance(budget=60)
        self.assertEqual([(r.state, r.note) for r in results], [("held", "check failed")])
        self.assertEqual(self.mod.queued({"last_run": {"results": [r._asdict() for r in results]}}), [])
        self.assertEqual((moves, self.fx.calls("setup-a.py")), ([], []))

    def test_hold_and_report_rows_never_move_and_say_why(self):
        url_a = self.fx.upstream("a")
        url_b = self.fx.upstream("b")
        old_a, old_b = self.fx.head("a"), self.fx.head("b")
        self.fx.clone("Harness/a", "a", old_a)
        self.fx.clone("PCB Tools/b", "b", old_b)
        self.fx.manifest([("Harness/a", url_a, old_a), ("PCB Tools/b", url_b, old_b)])
        self.fx.policy("Harness/a\thold the lab is pinned\t-\t-\nPCB Tools/b\treport Aster releases it\t-\t-\n")
        self.fx.push_commit("a", "second")
        self.fx.push_commit("b", "second")
        results, moves = self.advance()
        self.assertEqual(moves, [])
        states = {r.what: (r.state, r.note) for r in results}
        self.assertEqual(states["Harness/a"][0], "hold")
        self.assertIn("the lab is pinned", states["Harness/a"][1])
        self.assertEqual(states["PCB Tools/b"][0], "report")
        self.assertIn("available", states["PCB Tools/b"][1])
        self.assertIn("Harness/a\t%s\t%s\n" % (url_a, old_a), self.manifest_text())

    def test_out_of_time_leaves_a_move_pending(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        self.fx.push_commit("a", "second")
        results, moves = self.advance(budget=-1)
        self.assertEqual(results[0].state, "pending")
        self.assertEqual(moves, [])
        self.assertIn("Harness/a\t%s\t%s\n" % (url, old), self.manifest_text())

    def test_a_slow_installer_gets_the_budget_left_and_is_retried_with_more(self):
        # A runtime rebuild can outlast a session start's budget; that attempt
        # is rolled back and held, and a run with more time tries again.
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        # The tool gives an installer at least 5 s however small the budget,
        # so the sleep must outlast that floor to be cut off; at the old pin
        # the installer is quick, so the restore itself succeeds.
        self.fx.script("setup-a.py", "import os, time\nif 'second' in open(os.path.join(%r, 'README.md')).read(): time.sleep(8)"
                       % str(self.fx.dev / "Harness" / "a"))
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        new = self.fx.push_commit("a", "second")
        self.mod.INSTALL_MINIMUM = 1          # let a short budget reach the installer here
        self.mod.MOVE_MARGIN = 0
        started = time.monotonic()
        results, moves = self.advance(budget=2)
        self.assertLess(time.monotonic() - started, 40)
        self.assertEqual(results[0].state, "rolled back", results)
        self.assertIn("timed out", results[0].note)
        self.assertEqual(moves, [])
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev / "Harness" / "a").stdout.strip(), old)
        results, moves = self.advance(budget=60)
        self.assertEqual(results[0].state, "advanced", results)
        self.assertEqual(moves[0][2], new)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="update-tools-")
        self.fx = Fixture(Path(self.temporary.name).resolve())
        self.mod = load()
        # A stub sync that records the push it was asked for.
        sync = self.fx.dev / ".claude" / "hooks" / "sync.sh"
        sync.write_text("#!/usr/bin/env bash\necho \"$@\" >> \"$(dirname \"$0\")/sync.calls\"\nexit 0\n",
                        encoding="utf-8")
        # check reads the plugin registry; a test's own file, never this PC's.
        self.registry = self.fx.root / "installed_plugins.json"

    def tearDown(self):
        self.temporary.cleanup()

    def run_tool(self, *args):
        # --no-plugins: the plugin step is PluginTests' business, and the real
        # CLI on this PC would otherwise run for minutes inside every apply.
        extra = ["--no-plugins"] if args and args[0] == "apply" else []
        done = subprocess.run([sys.executable, str(TOOL), "--root", str(self.fx.dev), *args, *extra],
                              capture_output=True, text=True, timeout=300,
                              env=dict(ENV, DEVARNESS_UPDATE_PLUGIN_REGISTRY=str(self.registry)))
        return done.returncode, done.stdout + done.stderr

    def state(self):
        return json.loads((self.fx.dev / ".claude" / "hooks" / "update-tools.state").read_text(encoding="utf-8"))

    def write_state(self, data):
        (self.fx.dev / ".claude" / "hooks" / "update-tools.state").write_text(json.dumps(data), encoding="utf-8")

    def a_behind_upstream(self):
        url = self.fx.upstream("a")
        old = self.fx.head("a")
        self.fx.clone("Harness/a", "a", old)
        self.fx.manifest([("Harness/a", url, old)])
        return url, old, self.fx.push_commit("a", "second")

    def test_apply_refreshes_and_checks_the_catalogue_after_plugins(self):
        self.fx.manifest([])
        marker = self.fx.dev / "plugins-finished"
        self.fx.script("bin/library", "from pathlib import Path\n"
                       "if not Path(%r).exists(): sys.exit(1)" % str(marker))

        def plugins(*args):
            marker.touch()
            return []

        with mock.patch.object(self.mod, "update_plugins", side_effect=plugins):
            results, code = self.mod.run_apply(self.fx.dev, 1800, True, [])
        self.assertEqual(code, 0)
        self.assertEqual(self.fx.calls("bin/library"), ["refresh", "check", "coverage"])
        self.assertIn("healthy", [r.state for r in results if r.what == "library"])

    def test_catalogue_failure_is_reported_saved_and_stops_its_checks(self):
        self.fx.manifest([])
        self.fx.script("bin/library", "print('bad source metadata')", exit_code=1)
        results, code = self.mod.run_apply(self.fx.dev, 1800, False, [], plugins=False)
        self.assertEqual(code, 3)
        self.assertEqual(self.fx.calls("bin/library"), ["refresh"])
        failures = [r for r in results if r.what == "library" and r.state == "failed"]
        self.assertEqual(len(failures), 1)
        self.assertIn("bad source metadata", failures[0].note)
        self.assertIn(failures[0]._asdict(), self.state()["last_run"]["results"])

    def test_catalogue_coverage_failure_is_not_a_successful_update(self):
        self.fx.manifest([])
        self.fx.script("bin/library", "if sys.argv[1] == 'coverage': sys.exit(1)")
        results, code = self.mod.run_apply(self.fx.dev, 1800, False, [], plugins=False)
        self.assertEqual(code, 3)
        self.assertEqual(self.fx.calls("bin/library"), ["refresh", "check", "coverage"])
        self.assertTrue(any(r.what == "library" and r.state == "failed" for r in results))

    def test_exhausted_budget_leaves_catalogue_pending_without_starting_it(self):
        self.fx.manifest([])
        results, _ = self.mod.run_apply(self.fx.dev, 0, False, [], plugins=False)
        self.assertEqual(self.fx.calls("bin/library"), [])
        self.assertTrue(any(r.what == "library" and r.state == "pending" for r in results))

    def test_a_clone_that_times_out_leaves_the_run_its_reserve_and_is_recorded(self):
        # A slow link: the clone uses every second it is given, then times out.
        # The scan, the moves and the plugin step keep INSTALL_MINIMUM, and the
        # row is recorded so that later runs do not download it again.
        url = self.fx.upstream("a")
        sha = self.fx.head("a")
        self.fx.manifest([("Harness/a", url, sha)])
        real_git, real_time, used = self.mod.git, self.mod.time, []

        class Clock:                            # the module's time, plus what the clone used
            def __getattr__(self, name):
                return getattr(real_time, name)

            def monotonic(self):
                return real_time.monotonic() + sum(used)

        def slow_link(repo, *args, timeout=self.mod.LS_TIMEOUT):
            if args[:1] == ("clone",):
                used.append(timeout)
                return 124, "", "timed out after %ss" % timeout
            return real_git(repo, *args, timeout=timeout)

        self.mod.git, self.mod.time = slow_link, Clock()     # this test's own module
        results, _ = self.mod.run_apply(self.fx.dev, 1800, False, [], plugins=False)
        self.assertIn(("upstreams", "scanned"), [(r.what, r.state) for r in results], results)
        self.assertEqual(self.state()["clone_timeouts"]["Harness/a"]["sha"], sha)

    def test_only_naming_a_row_that_timed_out_clones_it_and_clears_the_record(self):
        url = self.fx.upstream("a")
        sha = self.fx.head("a")
        self.fx.manifest([("Harness/a", url, sha)])
        self.write_state({"clone_timeouts": {"Harness/a": {"at": "2026-09-26T01:00:00Z", "sha": sha}}})
        rc, out = self.run_tool("apply", "--budget", "600", "--only", "Harness/a")
        self.assertEqual(rc, 0, out)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev / "Harness" / "a").stdout.strip(), sha, out)
        self.assertNotIn("Harness/a", self.state().get("clone_timeouts", {}))

    def test_check_names_a_row_that_timed_out(self):
        url = self.fx.upstream("a")
        sha = self.fx.head("a")
        self.fx.manifest([("Harness/a", url, sha)])
        self.write_state({"clone_timeouts": {"Harness/a": {"at": "2026-09-26T01:00:00Z", "sha": sha}}})
        self.mod.plugin_registry = lambda: self.registry
        results, _ = self.mod.run_check(self.fx.dev)
        self.assertIn(("Harness/a", "absent", self.mod.UNFINISHED % "Harness/a"), results)

    def test_apply_moves_commits_the_manifest_alone_and_pushes_only_that(self):
        # The syncer's --push sweeps every uncommitted file into a commit first
        # (sync.sh push_repo), which mid-session would publish another
        # agent's half-written work; the tool pushes its own commit itself.
        url, old, new = self.a_behind_upstream()
        origin = self.fx.root / "origin.git"
        git("init", "-q", "--bare", "-b", "main", str(origin))
        git("remote", "add", "origin", origin.as_posix(), cwd=self.fx.dev)
        git("push", "-q", "-u", "origin", "main", cwd=self.fx.dev)
        (self.fx.dev / "stray.txt").write_text("not for the commit\n", encoding="utf-8")
        rc, out = self.run_tool("apply", "--force")
        self.assertEqual(rc, 0, out)
        subject = git("log", "-1", "--format=%s", cwd=self.fx.dev).stdout.strip()
        self.assertEqual(subject, "update-tools: a %s→%s" % (old[:7], new[:7]))
        files = git("show", "--stat", "--format=", "HEAD", cwd=self.fx.dev).stdout
        self.assertIn("repos.txt", files)
        self.assertNotIn("stray.txt", files)
        head = git("rev-parse", "HEAD", cwd=self.fx.dev).stdout.strip()
        self.assertEqual(git("rev-parse", "main", cwd=origin).stdout.strip(), head)
        self.assertTrue((self.fx.dev / "stray.txt").exists())
        self.assertFalse((self.fx.dev / ".claude" / "hooks" / "sync.calls").exists())
        self.assertIn("advanced", out)
        self.assertIn("pushed", out)

    def test_every_start_scans_and_moves_a_light_clone(self):
        # Every start checks for new pins, including a second start in the same hour.
        url, old, new = self.a_behind_upstream()
        rc, out = self.run_tool("apply", "--budget", "60")
        self.assertIn("advanced", out, out)
        newer = self.fx.push_commit("a", "third")
        rc, out = self.run_tool("apply", "--budget", "60")
        self.assertIn("advanced", out, out)
        self.assertIn(newer[:7], out)
        self.assertIn("Harness/a\t%s\t%s\n" % (url, newer),
                      (self.fx.dev / "Harness" / "repos.txt").read_text(encoding="utf-8"))

    def test_a_long_run_moves_what_a_start_left_pending(self):
        url, old, new = self.a_behind_upstream()
        self.fx.script("setup-a.py", "")
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        rc, out = self.run_tool("apply", "--budget", "60")
        self.assertIn("long run", out)                  # the start scanned and left it pending
        rc, out = self.run_tool("apply", "--budget", "1800")
        self.assertIn("advanced", out, out)
        rc, out = self.run_tool("apply", "--budget", "1800")
        self.assertNotIn("advanced", out)               # at upstream now: nothing to move
        self.assertIn("scanned", out)
        self.assertGreater(self.state()["last_long_run"], time.time() - 600)

    def test_an_offline_start_keeps_the_last_scan_and_says_how_little_it_reached(self):
        # Review Focus 5.
        url, old, new = self.a_behind_upstream()
        rc, out = self.run_tool("apply", "--force")
        first = self.state()["last_scan"]
        bare = self.fx.upstreams["a"][0]
        bare.rename(bare.with_name("a.gone"))           # the only upstream is out of reach
        rc, out = self.run_tool("apply")
        state = self.state()
        self.assertEqual(state["last_scan"], first)
        self.assertEqual((state["scan"]["reached"], state["scan"]["total"]), (0, 1))
        self.assertEqual(state["heads"][url], new)
        self.assertIn("0 of 1 reached", out)

    def test_a_budget_below_the_phase_two_minimum_only_follows(self):
        url, old, new = self.a_behind_upstream()
        rc, out = self.run_tool("apply", "--force", "--budget", "5")
        self.assertIn("not scanned", out)
        self.assertIn("Harness/a\t%s\t%s\n" % (url, old),
                      (self.fx.dev / "Harness" / "repos.txt").read_text(encoding="utf-8"))

    def test_force_retries_a_held_tool_after_its_installer_is_fixed(self):
        # A hold made at the 900 s cap can never be outbid by a larger budget,
        # so a deliberate run must be able to try again once the cause is fixed.
        url, old, new = self.a_behind_upstream()
        self.fx.script("setup-a.py", "import os\nsys.exit(1 if 'second' in open(os.path.join(%r, 'README.md')).read() else 0)"
                       % str(self.fx.dev / "Harness" / "a"))
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        rc, out = self.run_tool("apply", "--force")
        self.assertIn("rolled back", out)
        self.fx.script("setup-a.py", "")          # the installer is fixed
        rc, out = self.run_tool("apply", "--budget", "60")   # a start cannot retry an installer
        self.assertNotIn("advanced", out)
        rc, out = self.run_tool("apply", "--force")
        self.assertIn("advanced", out, out)
        self.assertNotIn("held", out)

    def test_a_session_start_budget_still_scans_after_phase_one(self):
        # session_start hands the tool at most 60 s; phase 1 spends some of
        # it, and what is left must still be enough to scan and move a light
        # tool; requiring the full original budget would prevent normal starts
        # from advancing anything after phase one consumes time.
        url, old, new = self.a_behind_upstream()
        rc, out = self.run_tool("apply", "--force", "--budget", "45")
        self.assertIn("advanced", out)
        self.assertNotIn("not scanned", out)

    def test_a_second_device_follows_the_pin_and_does_not_scan(self):
        url, old, new = self.a_behind_upstream()
        rc, out = self.run_tool("apply", "--force")
        self.assertEqual(rc, 0, out)
        # Device B: the same old clone, then the manifest the sync would bring.
        second = Fixture(self.fx.root / "B")
        second.upstreams = self.fx.upstreams
        second.clone("Harness/a", "a", old)
        (second.dev / "Harness" / "repos.txt").write_bytes((self.fx.dev / "Harness" / "repos.txt").read_bytes())
        newest = self.fx.push_commit("a", "third")     # upstream moved again; B must not take it
        done = subprocess.run([sys.executable, str(TOOL), "--root", str(second.dev), "apply", "--budget", "30", "--no-plugins"],
                              capture_output=True, text=True, timeout=120, env=ENV)
        self.assertIn("followed", done.stdout)
        self.assertEqual(git("rev-parse", "HEAD", cwd=second.dev / "Harness" / "a").stdout.strip(), new)

    def test_check_reports_without_writing_and_exits_one_when_behind(self):
        url, old, new = self.a_behind_upstream()
        before = git("rev-parse", "HEAD", cwd=self.fx.dev).stdout
        rc, out = self.run_tool("check")
        self.assertEqual(rc, 1, out)
        self.assertIn("behind", out)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev).stdout, before)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev / "Harness" / "a").stdout.strip(), old)
        rc, out = self.run_tool("check", "--json")
        self.assertEqual(json.loads(out)["rows"][0]["state"], "behind")

    def test_check_lists_a_clone_at_its_pin_and_upstream_as_current(self):
        url = self.fx.upstream("b")
        sha = self.fx.head("b")
        self.fx.clone("Harness/b", "b", sha)
        self.fx.manifest([("Harness/b", url, sha)])
        rc, out = self.run_tool("check", "--json")
        self.assertEqual(rc, 0, out)
        self.assertIn({"what": "Harness/b", "state": "current", "note": sha[:7]}, json.loads(out)["rows"])

    def test_check_names_a_tool_held_on_this_device_as_held_not_behind(self):
        # apply leaves a hold alone until upstream moves past it or --force,
        # so check calling it "behind" would promise a move that never comes.
        url, old, new = self.a_behind_upstream()
        self.write_state({"held": {"Harness/a": {"at": new, "reason": "after setup-a.py failed: boom",
                                              "when": "2026-09-24T04:35:53Z", "timeout": 900}}})
        rc, out = self.run_tool("check", "--json")
        rows = [r for r in json.loads(out)["rows"] if r["what"] == "Harness/a"]
        self.assertEqual(rows, [{"what": "Harness/a", "state": "held",
                                 "note": "%s→%s: after setup-a.py failed: boom" % (old[:7], new[:7])}])
        self.assertEqual(rc, 0, out)

    def test_check_lists_each_plugin_with_its_version_and_the_last_step(self):
        self.fx.manifest([])
        self.registry.write_text(json.dumps({"version": 2, "plugins": {
            "ecc@ecc": [{"scope": "local", "version": "2.2.2"}],
            "codex@openai-codex": [{"scope": "local", "version": "1.0.6"}]}}), encoding="utf-8")
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        self.write_state({"last_plugins": {"at": at, "changed": [], "failed": {"codex@openai-codex": "boom"}}})
        rc, out = self.run_tool("check", "--json")
        rows = {r["what"]: r for r in json.loads(out)["rows"]}
        self.assertEqual(rows["ecc@ecc"], {"what": "ecc@ecc", "state": "current", "note": "2.2.2, checked " + at})
        self.assertEqual(rows["codex@openai-codex"], {"what": "codex@openai-codex", "state": "failed",
                                                      "note": "1.0.6: boom"})
        self.assertEqual(rc, 0, out)

    def test_a_plugin_the_step_has_not_checked_for_a_day_is_unchecked(self):
        self.fx.manifest([])
        self.registry.write_text(json.dumps({"version": 2, "plugins": {"ecc@ecc": [{"version": "2.2.2"}]}}),
                                 encoding="utf-8")
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 2 * 86400))
        self.write_state({"last_plugins": {"at": at, "changed": []}})
        rc, out = self.run_tool("check", "--json")
        rows = {r["what"]: r for r in json.loads(out)["rows"]}
        self.assertEqual(rows["ecc@ecc"], {"what": "ecc@ecc", "state": "unchecked",
                                           "note": "2.2.2; last checked %s: update-tools apply --budget 1800" % at})

    def test_status_and_banner_read_the_saved_state_only(self):
        url, old, new = self.a_behind_upstream()
        rc, out = self.run_tool("banner")
        self.assertIn("never run", out)
        self.run_tool("apply", "--force")
        git("remote", "set-url", "origin", "https://127.0.0.1:9/none.git", cwd=self.fx.dev / "Harness" / "a")
        rc, out = self.run_tool("banner")
        self.assertEqual(rc, 0)
        self.assertIn("nothing pending", out)
        self.assertIn("a %s→%s" % (old[:7], new[:7]), out)
        rc, out = self.run_tool("status")
        self.assertIn("advanced", out)
        self.assertLess(max(len(line) for line in out.splitlines()), 200)

    def test_a_run_on_a_few_rows_is_not_the_scan_the_banner_dates(self):
        url, old, new = self.a_behind_upstream()
        rc, out = self.run_tool("apply", "--force", "--only", "Harness/none")
        state_text = (self.fx.dev / ".claude" / "hooks" / "update-tools.state").read_text(encoding="utf-8")
        self.assertNotIn("last_scan", state_text)
        rc, out = self.run_tool("apply")            # the next whole run scans and moves the clone
        self.assertIn("advanced", out)

    def test_a_lock_held_by_another_run_is_respected(self):
        url, old, new = self.a_behind_upstream()
        lock = self.fx.dev / ".claude" / "hooks" / "update-tools.lock"
        lock.write_text("pid %d since now\n" % os.getpid(), encoding="utf-8")   # alive: this test
        rc, out = self.run_tool("apply", "--force")
        self.assertEqual(rc, 0, out)
        self.assertIn("another update-tools", out)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev / "Harness" / "a").stdout.strip(), old)
        self.assertTrue(lock.exists())
        rc, out = self.run_tool("banner")
        self.assertIn("running", out)

    def test_a_lock_left_by_a_killed_run_is_taken_over(self):
        # taskkill /F skips the cleanup that removes the lock; two hours of
        # starts must not then do nothing.
        url, old, new = self.a_behind_upstream()
        dead = subprocess.Popen([sys.executable, "-c", ""])
        dead.wait()
        lock = self.fx.dev / ".claude" / "hooks" / "update-tools.lock"
        lock.write_text("pid %d since now\n" % dead.pid, encoding="utf-8")
        rc, out = self.run_tool("apply", "--force")
        self.assertIn("advanced", out)
        self.assertFalse(lock.exists())

    def test_a_refused_pin_commit_is_said_and_not_pushed(self):
        url, old, new = self.a_behind_upstream()
        hook = self.fx.dev / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        rc, out = self.run_tool("apply", "--force")
        self.assertIn("uncommitted", out)
        self.assertNotIn("pushed", out)

    def test_the_banner_names_pending_rows_counts_held_ones_and_dates_both_runs(self):
        at = time.time()
        self.write_state({"pending": {"Harness/docling": at, "Harness/laya": at},
                          "held_rows": ["Harness/i-have-adhd", "Harness/cwc-workshops"],
                          "last_scan": at - 120, "last_long_run": at - 20 * 3600,
                          "last_plugins": {"at": "2026-09-25T04:00:00Z", "changed": [], "failed": {}},
                          "last_run": {"at": "2026-09-25T09:00:00Z", "seconds": 9.0, "results": []}})
        rc, out = self.run_tool("banner")
        self.assertIn("updates: 2 pending (docling, laya), 2 held; scanned 2 min ago; long run 20 h ago", out)
        self.assertNotIn("degraded", out)

    def test_a_stale_long_run_an_old_pending_row_and_unchecked_plugins_degrade(self):
        at = time.time()
        self.write_state({"pending": {"Harness/docling": at - 50 * 3600}, "held_rows": [],
                          "last_scan": at, "last_long_run": at - 40 * 3600,
                          "last_run": {"at": "2026-09-25T09:00:00Z", "seconds": 9.0, "results": []}})
        rc, out = self.run_tool("banner")
        self.assertIn("  degraded: ", out)
        self.assertIn("the daily long run last ran 40 h ago", out)
        self.assertIn("waiting over 48 h: docling", out)
        self.assertIn("the plugins were never checked here", out)

    def test_an_offline_start_keeps_the_pending_rows_and_degrades(self):
        # Review Focus 5.
        url, old, new = self.a_behind_upstream()
        self.fx.script("setup-a.py", "")
        self.fx.policy("Harness/a\tauto\tsetup-a.py --install\t-\n")
        self.run_tool("apply", "--budget", "60")        # a start: its installer needs the long run
        since = self.state()["pending"]["Harness/a"]
        bare = self.fx.upstreams["a"][0]
        bare.rename(bare.with_name("a.gone"))
        self.run_tool("apply", "--budget", "60")        # offline now
        self.assertEqual(self.state()["pending"]["Harness/a"], since)
        rc, out = self.run_tool("banner")
        self.assertIn("1 pending (a)", out)
        self.assertIn("the last scan reached 0 of 1 upstreams", out)

    def test_a_report_row_whose_upstream_moved_is_counted_once_as_held(self):
        # Between Tasks 1 and 6 one report row read "1 report, 1 behind
        # upstream"; the key behind is retired, and a state that has it loses it.
        url, old, new = self.a_behind_upstream()
        self.fx.policy("Harness/a\treport Aster releases it\t-\t-\n")
        self.write_state({"behind": ["Harness/a"]})
        self.run_tool("apply", "--budget", "60")
        rc, out = self.run_tool("banner")
        self.assertIn("updates: nothing pending, 1 held;", out)
        self.assertNotIn("report", out)
        self.assertNotIn("behind", self.state())

    def test_pending_and_held_follow_the_last_known_heads_and_the_policy(self):
        # The plan's item 9: held is a row upstream moved past that will not
        # move by itself; pending is one that will, or has no clone at its pin.
        one, two = "1" * 40, "2" * 40
        rows = [self.mod.Row("Harness/" + name, "u/" + name, one, "")
                for name in ("auto", "report", "held", "gone", "current")]
        state = {"heads": {"u/auto": two, "u/report": two, "u/held": two, "u/current": one},
                 "held": {"Harness/held": {"at": two, "reason": "boom"}}, "pending": {"Harness/auto": 100.0}}
        policy = {"Harness/report": self.mod.Policy("report", "Aster releases it", None, None)}
        self.mod.clone_head = lambda root, row: None if row.path == "Harness/gone" else one
        self.mod.summarize(self.fx.dev, rows, policy, state)
        self.assertEqual(sorted(state["pending"]), ["Harness/auto", "Harness/gone"])
        self.assertEqual(state["pending"]["Harness/auto"], 100.0)      # waiting since the run that first saw it
        self.assertEqual(state["held_rows"], ["Harness/report", "Harness/held"])

    def test_a_launch_in_the_same_second_as_its_run_is_shown(self):
        # Both are one-second now_iso stamps, and a
        # start launches within the second its run ended, so > would hide it.
        state = {"last_run": {"at": "2026-09-26T09:00:00Z", "seconds": 9.0, "results": []},
                 "launched": {"at": "2026-09-26T09:00:00Z", "how": "DEVARNESS_update_daily", "for": ["docling", "laya"]}}
        # The stamps are UTC and the owner reads this device's clock (final review).
        local = dt.datetime(2026, 9, 26, 9, 0, tzinfo=dt.timezone.utc).astimezone().strftime("%H:%M")
        self.assertIn("  background run started %s (DEVARNESS_update_daily) for docling, laya" % local,
                      self.mod.banner_lines(state))
        state["launched"]["at"] = "2026-09-26T08:59:59Z"            # a launch a later run has answered
        self.assertEqual([line for line in self.mod.banner_lines(state) if "background run" in line], [])

    def test_a_save_cut_short_leaves_the_last_whole_state(self):
        # Final review: load_state reads half a file as {}, which forgets holds,
        # clone timeouts, stuck tools and the plugin record.
        self.mod.save_state(self.fx.dev, {"held": {"Harness/a": {"at": "abc"}}})
        write_text = Path.write_text

        def cut_short(path, text, *args, **kwargs):
            write_text(path, text[:len(text) // 2], *args, **kwargs)
            raise KeyboardInterrupt                   # a kill in the middle of the write
        with mock.patch.object(Path, "write_text", cut_short):
            with self.assertRaises(KeyboardInterrupt):
                self.mod.save_state(self.fx.dev, {"held": {}, "later": 1})
        self.assertEqual(self.mod.load_state(self.fx.dev), {"held": {"Harness/a": {"at": "abc"}}})
        # A half file is left in the ignored log folder, where no sync sweeps it.
        self.assertEqual(list((self.fx.dev / ".claude" / "hooks").glob("*.tmp")), [])

    def test_a_save_waits_out_a_reader_holding_the_state_open(self):
        # On Windows os.replace fails while another process reads the file.
        real, calls = os.replace, []

        def busy_twice(source, target):
            calls.append(target)
            if len(calls) <= 2:
                raise PermissionError(13, "in use")
            real(source, target)
        with mock.patch.object(self.mod.os, "replace", busy_twice):
            self.mod.save_state(self.fx.dev, {"later": 2})
        self.assertEqual((len(calls), self.mod.load_state(self.fx.dev)), (3, {"later": 2}))

    def test_a_row_gone_from_the_manifest_leaves_no_stuck_held_or_timeout(self):
        # Final review: a stuck row removed from repos.txt kept every start DEGRADED.
        one = "1" * 40
        rows = [self.mod.Row("Harness/kept", "u/kept", one, "")]
        state = {"stuck": {"Harness/gone": {"at": 1.0}, "Harness/kept": {"at": 1.0}},
                 "held": {"Harness/gone": {"at": one}}, "clone_timeouts": {"Harness/gone": {"sha": one}}}
        self.mod.clone_head = lambda root, row: one
        self.mod.summarize(self.fx.dev, rows, {}, state)
        self.assertEqual((list(state["stuck"]), state["held"], state["clone_timeouts"]),
                         (["Harness/kept"], {}, {}))
        self.assertIn("stuck: kept", self.mod.degraded(state))

    def test_a_folder_the_handler_cannot_mend_is_reported_not_raised(self):
        # Final review: on POSIX rmtree can hand the handler os.open, and
        # retrying os.open(target) raised TypeError, which nothing caught.
        folder = self.fx.root / "stuck.partial"
        folder.mkdir()
        error = PermissionError(13, "Permission denied", str(folder))

        def rmtree(path, **handlers):
            if "onexc" in handlers:
                handlers["onexc"](os.open, str(path), error)
            else:
                handlers["onerror"](os.open, str(path), (PermissionError, error, None))
        with mock.patch.object(self.mod.shutil, "rmtree", rmtree):
            gone, why = self.mod.remove_tree(folder)
        self.assertFalse(gone)
        self.assertIn("Permission denied", why)

    def test_a_rebase_in_progress_leaves_the_pins_where_they_are(self):
        # Final review: long runs now start by day, and a pin commit must not
        # land inside another session's stopped rebase or merge.
        url, old, new = self.a_behind_upstream()
        (self.fx.dev / ".git" / "rebase-merge").mkdir()
        rc, out = self.run_tool("apply", "--force")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=self.fx.dev).stdout.strip(), "manifest")
        self.assertIn(old, (self.fx.dev / "Harness" / "repos.txt").read_text(encoding="utf-8"))
        self.assertIn("rebase", out)

    def test_the_unfinished_note_asks_for_less_time_than_the_lock_lasts(self):
        # Final review: a run given 7200 s outlives the 2 h lock, and a second run takes it over.
        budget = int(re.search(r"--budget (\d+)", self.mod.UNFINISHED).group(1))
        self.assertLess(budget, self.mod.LOCK_STALE_HOURS * 3600)

    def test_the_banner_names_the_rows_it_reports_absent_or_cloned(self):
        # An aggregate count does not identify missing clones. One clone can
        # also be absent twice in a run, once in each phase.
        results = [("Harness/laya", "absent", "no clone; the background run clones it: update-tools apply --budget 1800"),
                   ("Harness/docling", "absent", "no clone; the background run clones it: update-tools apply --budget 1800"),
                   ("Harness/docling", "absent", "no clone yet; the long run clones it at its pin"),
                   ("Harness/herdr", "cloned", "partial clone at abc1234")]
        state = {"last_run": {"at": "2026-09-26T09:00:00Z", "seconds": 9.0,
                              "results": [{"what": w, "state": s, "note": n} for w, s, n in results]}}
        lines = self.mod.banner_lines(state)
        self.assertIn("  absent: docling, laya", lines)
        self.assertIn("  herdr partial clone at abc1234", lines)

    def test_a_pin_commit_that_needs_a_person_is_shown_whole(self):
        # Task 5: a restore that failed names the command that puts the files
        # back; a line cut at 200 characters would lose the command.
        why = ("NEEDS A PERSON: the branch moved while rebasing, and the index and files could not be "
               "put back (fatal: Unable to create 'C:/dev/.git/index.lock': File exists.): they are at "
               "0123456789ab, the branch at 89abcdef0123; put them back with: "
               "git -C \"C:/dev\" read-tree -m -u %s HEAD" % ("0123456789ab" + "c" * 28))
        state = {"unpushed": {"count": 1, "why": why},
                 "last_run": {"at": "2026-09-26T09:00:00Z", "seconds": 9.0, "results": []}}
        self.assertIn("  pin commit unpushed: 1 commit(s); " + why, self.mod.banner_lines(state))

    def test_a_failed_plugin_step_is_named_at_every_start(self):
        # A start never runs the plugin step, so its failures come from the state.
        state = {"last_plugins": {"at": "2026-09-25T04:00:00Z", "changed": [],
                                  "failed": {"marketplaces": "offline", "codex copies": "n8n skills differ"}},
                 "last_run": {"at": "2026-09-26T09:00:00Z", "seconds": 9.0, "results": []}}
        self.assertIn("  2 plugin steps failed: codex copies, marketplaces", self.mod.banner_lines(state))

    def unpushed_state(self, why):
        """A state with nothing else to degrade on, and one pin commit unpushed for why."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return {"last_run": {"at": now, "seconds": 9.0, "results": []}, "last_scan": time.time(),
                "last_long_run": time.time(), "last_plugins": {"at": now, "changed": [], "failed": {}},
                "unpushed": {"count": 1, "why": why}}

    def test_a_pin_commit_that_needs_a_person_degrades_the_start(self):
        # A partially moved shared index requires attention rather than READY.
        state = self.unpushed_state("NEEDS A PERSON: the branch moved while rebasing, and the index and files "
                                    "could not be put back (x): they are at a, the branch at b; put them back "
                                    "with: git -C \"C:/dev\" read-tree -m -u abc HEAD")
        self.assertIn("  degraded: the pin commit needs a person: its line above says what to run",
                      self.mod.banner_lines(state))

    def test_an_ordinary_unpushed_pin_commit_does_not_degrade_the_start(self):
        # It is pushed at a later run, or by hand: dev has no sweeping sync to carry it.
        state = self.unpushed_state("other commits are ahead of origin; push them by hand")
        self.assertEqual([line for line in self.mod.banner_lines(state) if "degraded" in line], [])

    def test_check_names_a_stuck_tool_and_a_failed_codex_copy(self):
        url = self.fx.upstream("b")
        sha = self.fx.head("b")
        self.fx.clone("Harness/b", "b", sha)
        self.fx.manifest([("Harness/b", url, sha)])
        self.registry.write_text(json.dumps({"plugins": {}}), encoding="utf-8")
        self.write_state({"stuck": {"Harness/b": {"at": sha, "reason": "setup-b.py failed: boom", "when": "t"}},
                          "last_plugins": {"at": "2026-09-24T08:00:00Z", "changed": [],
                                           "failed": {"codex copies": "Skill differs"}}})
        rc, out = self.run_tool("check", "--json")
        rows = {r["what"]: r for r in json.loads(out)["rows"]}
        self.assertEqual(rows["Harness/b"]["state"], "stuck")
        self.assertEqual(rows["codex copies"], {"what": "codex copies", "state": "failed", "note": "Skill differs"})

    def test_a_staged_unrelated_file_stays_staged_and_out_of_the_pin_commit(self):
        url, old, new = self.a_behind_upstream()
        (self.fx.dev / "other.txt").write_text("staged by another session\n", encoding="utf-8")
        git("add", "other.txt", cwd=self.fx.dev)
        rc, out = self.run_tool("apply", "--force")
        self.assertIn("advanced", out)
        files = git("show", "--stat", "--format=", "HEAD", cwd=self.fx.dev).stdout
        self.assertNotIn("other.txt", files)
        self.assertIn("other.txt", git("diff", "--cached", "--name-only", cwd=self.fx.dev).stdout)

    def with_origin(self):
        origin = self.fx.root / "origin.git"
        git("init", "-q", "--bare", "-b", "main", str(origin))
        git("remote", "add", "origin", origin.as_posix(), cwd=self.fx.dev)
        git("push", "-q", "-u", "origin", "main", cwd=self.fx.dev)
        return origin

    def other_device_commits(self, origin, edit):
        """Device B: a clone of origin, one commit made by edit(folder), pushed first."""
        other = self.fx.root / "B-dev"
        git("clone", "-q", origin.as_posix(), str(other))
        edit(other)
        git("add", "-A", cwd=other)
        git("commit", "-qm", "device B", cwd=other)
        git("push", "-q", "origin", "main", cwd=other)

    def two_adjacent_rows(self):
        url_a, url_b = self.fx.upstream("a"), self.fx.upstream("b")
        old_a, old_b = self.fx.head("a"), self.fx.head("b")
        self.fx.clone("Harness/a", "a", old_a)
        self.fx.clone("Harness/b", "b", old_b)
        self.fx.manifest([("Harness/a", url_a, old_a), ("Harness/b", url_b, old_b)])
        return url_a, url_b, old_a, old_b

    def test_a_pins_only_race_is_reapplied_not_a_conflict(self):
        # M13, reproduced while planning: B moves pin b and pushes; this device
        # moves pin a on the next line. A plain rebase conflicts on the adjacent
        # lines; update-tools writes its own move into B's repos.txt instead.
        url_a, url_b, old_a, old_b = self.two_adjacent_rows()
        origin = self.with_origin()
        new_b = self.fx.push_commit("b", "second b")

        def move_b(folder):
            # Row b by its URL: a and b made in one second share a first commit,
            # and replacing the bare sha would move row a too. write_bytes, as
            # write_text's newline= needs Python 3.10 and the Mac's may be 3.9.
            path = folder / "Harness" / "repos.txt"
            row = "%s\t%s" % (url_b, old_b)
            path.write_bytes(path.read_text(encoding="utf-8").replace(row, "%s\t%s" % (url_b, new_b)).encode("utf-8"))
        self.other_device_commits(origin, move_b)
        new_a = self.fx.push_commit("a", "second a")
        (self.fx.dev / "stray.txt").write_text("another session's edit\n", encoding="utf-8")
        (self.fx.dev / "staged.txt").write_text("staged by another session\n", encoding="utf-8")
        git("add", "staged.txt", cwd=self.fx.dev)
        rc, out = self.run_tool("apply", "--force", "--only", "Harness/a")
        self.assertIn("rebased onto origin and pushed", out)
        remote = git("show", "main:Harness/repos.txt", cwd=origin).stdout
        self.assertIn("Harness/a\t%s\t%s\n" % (url_a, new_a), remote)
        self.assertIn("Harness/b\t%s\t%s\n" % (url_b, new_b), remote)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev).stdout, git("rev-parse", "main", cwd=origin).stdout)
        self.assertEqual((self.fx.dev / "stray.txt").read_text(encoding="utf-8"), "another session's edit\n")
        self.assertIn("staged.txt", git("diff", "--cached", "--name-only", cwd=self.fx.dev).stdout)

    def test_other_unpushed_work_leaves_the_pin_commit_to_the_sync_and_says_so(self):
        url_a, url_b, old_a, old_b = self.two_adjacent_rows()
        origin = self.with_origin()
        self.other_device_commits(origin, lambda folder: (folder / "theirs.md").write_text("B\n", encoding="utf-8"))
        (self.fx.dev / "mine.md").write_text("another agent's work\n", encoding="utf-8")
        git("add", "mine.md", cwd=self.fx.dev)
        git("commit", "-q", "--only", "mine.md", "-m", "another agent's commit", cwd=self.fx.dev)
        self.fx.push_commit("a", "second a")
        rc, out = self.run_tool("apply", "--force", "--only", "Harness/a")
        self.assertIn("pin commit unpushed: other commits are ahead of origin", out)
        self.assertEqual(self.state()["unpushed"]["count"], 1)
        self.assertIn("another agent's commit", git("log", "-2", "--format=%s", cwd=self.fx.dev).stdout)

    def test_another_agents_commit_is_never_pushed_with_the_pin(self):
        # An unchanged origin does not authorize publishing unrelated local commits.
        self.two_adjacent_rows()
        origin = self.with_origin()
        released = git("rev-parse", "main", cwd=origin).stdout
        (self.fx.dev / "mine.md").write_text("another agent's work\n", encoding="utf-8")
        git("add", "mine.md", cwd=self.fx.dev)
        git("commit", "-q", "--only", "mine.md", "-m", "another agent's commit", cwd=self.fx.dev)
        self.fx.push_commit("a", "second a")
        rc, out = self.run_tool("apply", "--force", "--only", "Harness/a")
        self.assertEqual(git("rev-parse", "main", cwd=origin).stdout, released, out)
        self.assertIn("pin commit unpushed: other commits are ahead of origin", out)
        self.assertTrue(git("log", "-1", "--format=%s", cwd=self.fx.dev).stdout.startswith("update-tools: a "))

    def test_a_local_edit_where_origin_changed_blocks_the_rebase_and_touches_nothing(self):
        # Review Focus 2.
        self.two_adjacent_rows()
        (self.fx.dev / "shared.md").write_text("one\n", encoding="utf-8")
        git("add", "shared.md", cwd=self.fx.dev)
        git("commit", "-qm", "shared", cwd=self.fx.dev)
        origin = self.with_origin()
        self.other_device_commits(origin, lambda folder: (folder / "shared.md").write_text("theirs\n", encoding="utf-8"))
        (self.fx.dev / "shared.md").write_text("mine, unsaved\n", encoding="utf-8")
        self.fx.push_commit("a", "second a")
        rc, out = self.run_tool("apply", "--force", "--only", "Harness/a")
        self.assertIn("pin commit unpushed: local edits where origin changed a file", out)
        self.assertEqual((self.fx.dev / "shared.md").read_text(encoding="utf-8"), "mine, unsaved\n")
        self.assertTrue(git("log", "-1", "--format=%s", cwd=self.fx.dev).stdout.startswith("update-tools: a "))
        # Once the edit is saved elsewhere, the next run carries the pin and the mark clears.
        git("checkout", "--", "shared.md", cwd=self.fx.dev)
        rc, out = self.run_tool("apply", "--only", "Harness/a")
        self.assertIn("rebased onto origin and pushed", out)
        self.assertNotIn("unpushed", self.state())

    def test_a_scratch_index_that_fails_stops_the_rebase_and_touches_nothing(self):
        # A scratch read-tree that fails and cleans up its lock (a refused
        # rename, a full disk) leaves no scratch index: update-index then
        # refuses, write-tree writes the empty tree, and moving the branch to a
        # commit of it would delete every clean file in the shared tree.
        self.a_pin_commit_behind_origin()
        head = git("rev-parse", "HEAD", cwd=self.fx.dev).stdout
        real_git = self.mod.git

        def failing_scratch(repo, *args, timeout=self.mod.LS_TIMEOUT, index=None):
            if index and args[:1] == ("read-tree",):
                return 128, "", "fatal: unable to write new index file"
            return real_git(repo, *args, timeout=timeout, index=index)
        self.mod.git = failing_scratch                      # this test's own module
        why = self.mod.rebase_pins(self.fx.dev, "main", time.monotonic() + 600)
        self.assertTrue(why.startswith("could not rebuild the pin commit"), why)
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev).stdout, head)
        self.assertTrue((self.fx.dev / ".gitignore").is_file())
        self.assertEqual(git("status", "--porcelain", "--untracked-files=no", cwd=self.fx.dev).stdout, "")

    def a_pin_commit_behind_origin(self, *tracked, change=None):
        """This device's pin commit of a, made by hand, after device B moved origin:
        by change(folder), or by adding theirs.md. tracked files are committed first."""
        url_a, url_b, old_a, old_b = self.two_adjacent_rows()
        for name in tracked:
            (self.fx.dev / name).write_text("one\n", encoding="utf-8")
            git("add", name, cwd=self.fx.dev)
            git("commit", "-qm", name, cwd=self.fx.dev)
        origin = self.with_origin()
        self.other_device_commits(origin, change or (lambda folder: (folder / "theirs.md").write_text("B\n", encoding="utf-8")))
        manifest = self.fx.dev / "Harness" / "repos.txt"
        manifest.write_bytes(self.mod.set_pin(manifest.read_text(encoding="utf-8"), url_a, "c" * 40).encode("utf-8"))
        git("commit", "-q", "-m", "update-tools: a pin", "--", "Harness/repos.txt", cwd=self.fx.dev)
        return origin

    def test_with_too_little_time_left_no_rebase_is_attempted(self):
        # I3: a start has 60 s and is killed 5 s after, and a kill inside the
        # two-way read-tree leaves the shared index half-written and locked.
        self.two_adjacent_rows()
        origin = self.with_origin()
        self.other_device_commits(origin, lambda folder: (folder / "theirs.md").write_text("B\n", encoding="utf-8"))
        self.fx.push_commit("a", "second a")
        real_git, real_time, dev, spent, calls = self.mod.git, self.mod.time, self.fx.dev, [], []

        class Clock:                            # the module's time; the first push finds the run nearly spent
            def __getattr__(self, name):
                return getattr(real_time, name)

            def monotonic(self):
                return real_time.monotonic() + sum(spent)

        def recorded(repo, *args, timeout=self.mod.LS_TIMEOUT, index=None):
            if repo == dev:
                calls.append(args[0])
                if args[0] == "push" and not spent:
                    spent.append(600 - self.mod.MOVE_MARGIN)
            return real_git(repo, *args, timeout=timeout, index=index)
        self.mod.git, self.mod.time = recorded, Clock()      # this test's own module
        results, _ = self.mod.run_apply(dev, 600, True, ["Harness/a"], plugins=False)
        self.assertIn(("repos.txt", "unpushed"), [(r.what, r.state) for r in results], results)
        self.assertNotIn("fetch", calls)
        self.assertNotIn("read-tree", calls)
        self.assertFalse((dev / "theirs.md").exists())

    def test_a_paused_sync_leaves_the_pin_commit_where_it_is(self):
        # I4: sync.sh returns at once while sync.off exists (sync.sh:544).
        self.a_pin_commit_behind_origin()
        (self.fx.dev / ".claude" / "hooks" / "sync.off").write_text("", encoding="utf-8")
        head = git("rev-parse", "HEAD", cwd=self.fx.dev).stdout
        why = self.mod.rebase_pins(self.fx.dev, "main", time.monotonic() + 600)
        self.assertEqual(why, "the sync is paused: .claude/hooks/sync.off")
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev).stdout, head)
        self.assertFalse((self.fx.dev / "theirs.md").exists())

    def test_a_commit_made_during_the_rebase_stays_on_the_branch_with_its_files(self):
        # C1: another session's end sweep commits just after ahead() read the
        # branch; the compare-and-swap must guard everything from that read on.
        self.a_pin_commit_behind_origin("notes.md")
        real_git, dev, fired = self.mod.git, self.fx.dev, []

        def racing(repo, *args, timeout=self.mod.LS_TIMEOUT, index=None):
            result = real_git(repo, *args, timeout=timeout, index=index)
            if args[:1] == ("log",) and not fired:
                fired.append(1)
                (dev / "notes.md").write_text("another session's commit\n", encoding="utf-8")
                git("commit", "-q", "-m", "another session", "--", "notes.md", cwd=dev)
            return result
        self.mod.git = racing                              # this test's own module
        why = self.mod.rebase_pins(dev, "main", time.monotonic() + 600)
        self.assertEqual(why, "the branch moved while rebasing")
        self.assertIn("another session", git("log", "--format=%s", "main", cwd=dev).stdout)
        self.assertEqual((dev / "notes.md").read_text(encoding="utf-8"), "another session's commit\n")
        self.assertEqual(git("status", "--porcelain", "--untracked-files=no", cwd=dev).stdout, "")

    def test_another_sessions_row_in_the_pin_commit_stops_the_rebase_and_stays(self):
        # C2: commit_manifest commits the whole file, so a row another session
        # was adding rides in the pin commit; re-applying pins alone would drop it.
        url_a, url_b, old_a, old_b = self.two_adjacent_rows()
        origin = self.with_origin()
        self.other_device_commits(origin, lambda folder: (folder / "theirs.md").write_text("B\n", encoding="utf-8"))
        manifest = self.fx.dev / "Harness" / "repos.txt"
        row_c = "Harness/c\thttps://example.invalid/c.git\t" + "d" * 40
        with manifest.open("ab") as handle:              # another session adding a tool, uncommitted
            handle.write((row_c + "\n").encode("utf-8"))
        self.fx.push_commit("a", "second a")
        rc, out = self.run_tool("apply", "--force", "--only", "Harness/a")
        self.assertIn("pin commit unpushed: repos.txt has edits beside the pins", out)
        self.assertIn(row_c, manifest.read_text(encoding="utf-8"))
        self.assertIn(row_c, git("show", "HEAD:Harness/repos.txt", cwd=self.fx.dev).stdout)
        self.assertFalse((self.fx.dev / "theirs.md").exists())

    def test_a_merge_base_git_cannot_give_stops_the_rebase_and_the_row_stays(self):
        # Fix round 2: an empty base made "show :Harness/repos.txt" read the shared
        # index, which equals the pin commit, so C2's guard passed and the row
        # another session was adding was deleted from the files and from HEAD.
        url_a, url_b, old_a, old_b = self.two_adjacent_rows()
        origin = self.with_origin()
        self.other_device_commits(origin, lambda folder: (folder / "theirs.md").write_text("B\n", encoding="utf-8"))
        dev = self.fx.dev
        manifest = dev / "Harness" / "repos.txt"
        row_c = "Harness/c\thttps://example.invalid/c.git\t" + "d" * 40
        with manifest.open("ab") as handle:              # another session adding a tool, uncommitted
            handle.write((row_c + "\n").encode("utf-8"))
        self.mod.write_pins(dev, url_a, "c" * 40)          # the move, as advance() writes and commits it
        self.mod.commit_manifest(dev, [("Harness/a", old_a, "c" * 40)])
        head = git("rev-parse", "HEAD", cwd=dev).stdout
        real_git = self.mod.git

        def no_merge_base(repo, *args, timeout=self.mod.LS_TIMEOUT, index=None):
            if args[:1] == ("merge-base",):
                return 124, "", "timed out after 1.0s"
            return real_git(repo, *args, timeout=timeout, index=index)
        self.mod.git = no_merge_base                     # this test's own module
        why = self.mod.rebase_pins(dev, "main", time.monotonic() + 600)
        self.assertIn(row_c, manifest.read_text(encoding="utf-8"))
        self.assertIn(row_c, git("show", "HEAD:Harness/repos.txt", cwd=dev).stdout)
        self.assertEqual(git("rev-parse", "HEAD", cwd=dev).stdout, head)
        self.assertTrue(why.startswith("could not find the merge base"), why)

    def test_a_version_of_repos_txt_git_cannot_read_stops_the_rebase(self):
        # Fix round 2: an empty read never stands in for a version of repos.txt.
        # Origin's, the merge base's and this device's are read in that order.
        for which in range(3):
            with self.subTest(which=which):
                self.tearDown()
                self.setUp()                             # a fresh fixture and module for each
                self.a_pin_commit_behind_origin()
                dev = self.fx.dev
                head = git("rev-parse", "HEAD", cwd=dev).stdout
                real_git, shows = self.mod.git, []

                def unreadable(repo, *args, timeout=self.mod.LS_TIMEOUT, index=None):
                    if args[:1] == ("show",):
                        shows.append(args[1])
                        if len(shows) == which + 1:
                            return 128, "", "fatal: unable to read"
                    return real_git(repo, *args, timeout=timeout, index=index)
                self.mod.git = unreadable
                why = self.mod.rebase_pins(dev, "main", time.monotonic() + 600)
                self.assertEqual(git("rev-parse", "HEAD", cwd=dev).stdout, head)
                self.assertTrue(why.startswith("could not read"), why)

    def test_origin_moving_mid_rebase_is_never_reverted(self):
        # Fix round 3: git resolved refs/remotes/origin/main again at every call,
        # so a fetch in between (another session's sync, an editor's auto-fetch)
        # gave the pin commit origin's new tip as parent and the old tip's tree.
        def add_a_file(other):
            (other / "theirs2.md").write_text("B2\n", encoding="utf-8")

        def move_pin_b(other):
            path = other / "Harness" / "repos.txt"
            url_b = self.fx.upstreams["b"][0].as_posix()
            path.write_bytes(self.mod.set_pin(path.read_text(encoding="utf-8"), url_b, "e" * 40).encode("utf-8"))
        for after, change in (("read-tree", add_a_file), ("show", move_pin_b)):
            with self.subTest(after=after):
                self.tearDown()
                self.setUp()                             # a fresh fixture and module for each
                self.a_pin_commit_behind_origin()
                dev, other, fired = self.fx.dev, self.fx.root / "B-dev", []
                real_git = self.mod.git

                def racing(repo, *args, timeout=self.mod.LS_TIMEOUT, index=None):
                    result = real_git(repo, *args, timeout=timeout, index=index)
                    if args[:1] == (after,) and not fired:
                        fired.append(1)                  # device B pushes again, and a fetch lands here
                        change(other)
                        git("add", "-A", cwd=other)
                        git("commit", "-qm", "device B again", cwd=other)
                        git("push", "-q", "origin", "main", cwd=other)
                        git("fetch", "-q", "origin", "main", cwd=dev)
                    return result
                self.mod.git = racing                    # this test's own module
                why = self.mod.rebase_pins(dev, "main", time.monotonic() + 600)
                self.assertTrue(fired)
                if not why:                              # a pin commit changes this device's pin alone
                    url_a = self.fx.upstreams["a"][0].as_posix()
                    parent, head = (git("show", rev + ":Harness/repos.txt", cwd=dev).stdout for rev in ("HEAD~1", "HEAD"))
                    self.assertEqual(git("diff", "--name-only", "HEAD~1", "HEAD", cwd=dev).stdout, "Harness/repos.txt\n")
                    self.assertEqual(self.mod.set_pin(parent, url_a, "c" * 40), head)

    def test_an_origin_tip_git_cannot_resolve_stops_the_rebase(self):
        self.a_pin_commit_behind_origin()
        dev = self.fx.dev
        head = git("rev-parse", "HEAD", cwd=dev).stdout
        real_git = self.mod.git

        def unresolved(repo, *args, timeout=self.mod.LS_TIMEOUT, index=None):
            if args[:1] == ("rev-parse",) and any("refs/remotes/origin/" in arg for arg in args):
                return 128, "", "fatal: Needed a single revision"
            return real_git(repo, *args, timeout=timeout, index=index)
        self.mod.git = unresolved                        # this test's own module
        why = self.mod.rebase_pins(dev, "main", time.monotonic() + 600)
        self.assertEqual(git("rev-parse", "HEAD", cwd=dev).stdout, head)
        self.assertTrue(why.startswith("could not read origin's tip"), why)

    def test_an_unstaged_deletion_of_a_file_origin_changed_stops_the_rebase(self):
        # I2: git's two-way merge takes a missing file as up to date, so the
        # read-tree alone would bring back a file another session deleted.
        self.a_pin_commit_behind_origin("gone.md", change=lambda folder: (folder / "gone.md").write_text(
            "theirs\n", encoding="utf-8"))
        (self.fx.dev / "gone.md").unlink()                 # another session deletes it, not yet staged
        head = git("rev-parse", "HEAD", cwd=self.fx.dev).stdout
        why = self.mod.rebase_pins(self.fx.dev, "main", time.monotonic() + 600)
        self.assertTrue(why.startswith("local edits where origin changed a file"), why)
        self.assertFalse((self.fx.dev / "gone.md").exists())
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.fx.dev).stdout, head)

    def branch_moved_mid_rebase(self, held):
        """Another session commits between the two-way read-tree and update-ref,
        and its git holds index.lock through the first `held` restores (I1)."""
        self.a_pin_commit_behind_origin("notes.md")
        real_git, dev, moves = self.mod.git, self.fx.dev, []
        lock = dev / ".git" / "index.lock"

        def racing(repo, *args, timeout=self.mod.LS_TIMEOUT, index=None):
            two_way = args[:3] == ("read-tree", "-m", "-u")
            if two_way and moves and len(moves) <= held:
                lock.write_text("", encoding="utf-8")
            result = real_git(repo, *args, timeout=timeout, index=index)
            if lock.exists():
                lock.unlink()
            if two_way:
                moves.append(1)
                if len(moves) == 1:
                    (dev / "notes.md").write_text("another session's commit\n", encoding="utf-8")
                    git("commit", "-q", "-m", "another session", "--", "notes.md", cwd=dev)
            return result
        self.mod.git = racing                              # this test's own module
        return self.mod.rebase_pins(dev, "main", time.monotonic() + 600)

    def test_a_branch_moved_mid_rebase_gets_its_files_back_once_the_lock_clears(self):
        why = self.branch_moved_mid_rebase(held=1)
        dev = self.fx.dev
        self.assertEqual(why, "the branch moved while rebasing")
        self.assertEqual(git("diff", "--cached", "--name-status", cwd=dev).stdout, "")
        self.assertEqual(git("log", "-1", "--format=%s", cwd=dev).stdout.strip(), "another session")
        self.assertFalse((dev / "theirs.md").exists())

    def test_files_left_half_moved_are_named_with_the_command_that_restores_them(self):
        why = self.branch_moved_mid_rebase(held=99)
        dev = self.fx.dev
        self.assertTrue(why.startswith("NEEDS A PERSON: "), why)
        command = re.search(r'git -C "[^"]+" read-tree -m -u ([0-9a-f]{40}) HEAD$', why)
        self.assertIsNotNone(command, why)
        self.assertNotEqual(git("diff", "--cached", "--name-status", cwd=dev).stdout, "")
        git("read-tree", "-m", "-u", command.group(1), "HEAD", cwd=dev)     # the command it names
        self.assertEqual(git("diff", "--cached", "--name-status", cwd=dev).stdout, "")
        self.assertFalse((dev / "theirs.md").exists())


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="update-tools-")
        self.fx = Fixture(Path(self.temporary.name).resolve())
        self.mod = load()
        self.bin = self.fx.root / "fakebin"
        self.bin.mkdir()
        self.registry = self.fx.root / "installed_plugins.json"
        self.registry.write_text(json.dumps({"version": 2, "plugins": {"ecc@ecc": {}, "superpowers@claude-plugins-official": {}}}),
                                 encoding="utf-8")
        self.log = self.fx.dev / ".claude" / "hooks" / "update-tools" / "plugins.log"
        self.saved_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved_env)
        self.temporary.cleanup()

    def fake_claude(self, body):
        program = self.bin / "claude.py"
        program.write_text("import sys\nopen(%r, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n%s\n"
                           % (str(self.fx.root / "claude.calls"), body), encoding="utf-8")
        if os.name == "nt":
            (self.bin / "claude.cmd").write_text('@"%s" "%s" %%*\r\n' % (sys.executable, program), newline="")
        else:
            launcher = self.bin / "claude"
            launcher.write_text("#!/bin/sh\nexec %s %s \"$@\"\n" % (sys.executable, program))
            launcher.chmod(0o755)

    def run_plugins(self, budget=600, state=None):
        os.environ["PATH"] = str(self.bin) + os.pathsep + self.saved_env["PATH"]
        os.environ["DEVARNESS_UPDATE_PLUGIN_REGISTRY"] = str(self.registry)
        return self.mod.update_plugins(self.fx.dev, {} if state is None else state,
                                       time.monotonic() + budget, self.log)

    def test_a_plugin_that_fails_to_update_is_remembered_for_check(self):
        # The next start's run replaces last_run, so the failure must live
        # in last_plugins or check would call the plugin current.
        self.fake_claude("import sys\nsys.exit(1 if 'ecc@ecc' in sys.argv else 0)")
        state = {}
        self.run_plugins(state=state)
        self.assertEqual(sorted(state["last_plugins"]["failed"]), ["ecc@ecc"])

    def test_every_marketplace_and_plugin_is_updated_with_yes_and_json(self):
        self.fake_claude("print('ok')")
        results = self.run_plugins()
        calls = (self.fx.root / "claude.calls").read_text(encoding="utf-8").splitlines()
        self.assertIn("plugin marketplace update", calls)
        self.assertIn("plugin update -y --json ecc@ecc", calls)
        self.assertIn("plugin update -y --json superpowers@claude-plugins-official", calls)
        self.assertEqual(results[-1].what, "plugins")

    def test_a_hung_cli_costs_at_most_the_timeout(self):
        self.fake_claude("import time\ntime.sleep(120)")
        self.mod.PLUGIN_TIMEOUT = 2
        started = time.monotonic()
        results = self.run_plugins()
        self.assertLess(time.monotonic() - started, 20)
        self.assertIn("timed out", " ".join(r.note for r in results))

    def test_a_step_the_run_did_not_reach_keeps_its_earlier_failure(self):
        # M4: a step cut short kept nothing of what the last run knew.
        self.fake_claude("print('ok')")
        self.mod.PLUGIN_TIMEOUT = 1000           # longer than the budget: no step is reached
        state = {"last_plugins": {"at": "2026-09-24T04:00:00Z", "changed": [],
                                  "failed": {"codex copies": "n8n skills differ: n8n-code-python"}}}
        self.run_plugins(budget=600, state=state)
        self.assertEqual(state["last_plugins"]["failed"], {"codex copies": "n8n skills differ: n8n-code-python"})

    def test_the_failure_of_a_plugin_no_longer_installed_goes(self):
        # A plugin removed from the registry is no longer retried; discard its
        # stale failure instead of keeping it in every banner.
        self.fake_claude("print('ok')")
        state = {"last_plugins": {"at": "2026-09-24T04:00:00Z", "changed": [],
                                  "failed": {"gone@nowhere": "boom", "codex copies": "n8n skills differ"}}}
        self.run_plugins(state=state)
        self.assertEqual(state["last_plugins"]["failed"], {"codex copies": "n8n skills differ"})
        state["last_run"] = {"at": "2026-09-26T09:00:00Z", "seconds": 1.0, "results": []}
        self.assertNotIn("gone@nowhere", "\n".join(self.mod.banner_lines(state)))
        self.fx.manifest([])                               # update-tools check over this fixture
        self.mod.save_state(self.fx.dev, state)
        rows, _ = self.mod.run_check(self.fx.dev)
        self.assertNotIn("gone@nowhere", [row.what for row in rows])

    def test_a_registry_that_cannot_be_read_drops_no_failure(self):
        # Only a registry that was read says a plugin is gone.
        self.fake_claude("print('ok')")
        self.registry.write_text("{not json", encoding="utf-8")
        state = {"last_plugins": {"at": "2026-09-24T04:00:00Z", "changed": [], "failed": {"ecc@ecc": "boom"}}}
        self.run_plugins(state=state)
        self.assertEqual(state["last_plugins"]["failed"], {"ecc@ecc": "boom"})

    def test_the_plugin_step_waits_for_a_long_run(self):
        # Each plugin call takes 15–25 s here and there are eleven of them; a
        # start with 60 s would be killed inside the step and nothing saved.
        # Below the long-run minimum the step makes no call at all.
        self.fake_claude("print('ok')")
        results = self.run_plugins(budget=100)
        self.assertFalse((self.fx.root / "claude.calls").exists())
        self.assertEqual(results[0].state, "pending")
        self.assertIn("long run", results[0].note)

    def test_no_cli_is_a_note_not_an_error(self):
        os.environ["PATH"] = str(self.bin)
        results = self.mod.update_plugins(self.fx.dev, {}, time.monotonic() + 60, self.log)
        self.assertEqual(results[0].state, "skipped")
        self.assertIn("claude", results[0].note)


class PromptMasterInstallerTests(unittest.TestCase):
    def test_install_copies_the_skill_and_check_sees_a_difference(self):
        with tempfile.TemporaryDirectory(prefix="update-tools-") as tmp:
            dev = Path(tmp) / "dev"
            src = dev / "Harness" / "prompt-master" / "skills" / "prompt-master"
            src.mkdir(parents=True)
            (src / "SKILL.md").write_text("one\n", encoding="utf-8")
            (src / "references").mkdir()
            (src / "references" / "a.md").write_text("ref\n", encoding="utf-8")
            (dev / ".claude" / "skills").mkdir(parents=True)
            script = ROOT / "Harness" / "setup-prompt-master.py"
            env = dict(ENV, DEVARNESS_ROOT=str(dev))
            done = subprocess.run([sys.executable, str(script), "--install"], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual((dev / ".claude" / "skills" / "prompt-master" / "references" / "a.md").read_text(encoding="utf-8"), "ref\n")
            done = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(done.returncode, 0)
            (src / "SKILL.md").write_text("two\n", encoding="utf-8")
            done = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(done.returncode, 1)
            self.assertIn("SKILL.md", done.stdout)


if __name__ == "__main__":
    unittest.main()
