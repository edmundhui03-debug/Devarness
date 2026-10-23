#!/usr/bin/env python3
"""dev-check runs every checker from one entry point and fails only on a gate.

Run: python3 Harness/tests/test_dev_check.py

The table and CLI run throwaway commands, including a failing slow gate.
The outer dev-check run verifies the real checkout; repeating it from this
suite used several minutes of the library-tests deadline.
"""
from contextlib import redirect_stdout
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "Harness" / "bin" / "dev-check"


def load():
    loader = importlib.machinery.SourceFileLoader("dev_check", str(TOOL))
    spec = importlib.util.spec_from_loader("dev_check", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def py(code):
    return [sys.executable, "-c", code]


class TableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load()

    def check(self, name, kind, code, bound=30, slow=False, tolerate=()):
        return self.tool.Check(name, kind, py(code), bound, slow, tolerate)

    def run_plan(self, plan, **options):
        return self.tool.run(plan, ROOT, **options)

    def test_library_failure_is_a_gate_not_information(self):
        row = next(r for r in self.tool.PLAN if r.name == 'library-check')
        self.assertEqual(row.kind, self.tool.GATE)
        bad = row._replace(argv=py('import sys; sys.exit(1)'))
        results, code = self.run_plan([bad])
        self.assertEqual((code, results[0].status), (1, 'FAIL'))

    def test_library_coverage_is_a_gate(self):
        # dev reaches every tool through the library; a tool with no entry fails
        # the run (design spec, "Every tool is reached through the library").
        row = next(r for r in self.tool.PLAN if r.name == 'library-coverage')
        self.assertEqual(row, self.tool.Check("library-coverage", self.tool.GATE,
                                              ["python", "Harness/bin/library", "coverage"], 60, False, ()))

    def test_the_names_publishing_reverse_and_pick_gates_are_rows(self):
        # Owner, 9 October: no old name anywhere, publishable one day, the
        # reverse tools ready whenever he needs them, and the library picks right.
        G = self.tool.GATE
        for row in (self.tool.Check("names-audit", G, ["python", "Harness/names-audit.py"], 60, False, ()),
                    self.tool.Check("publishable", G, ["python", "Harness/publish-check.py"], 60, False, ()),
                    self.tool.Check("reverse-ready", G, ["python", "Harness/setup-reverse.py", "--check", "--doctor"],
                                    600, False, ()),
                    self.tool.Check("library-picks", G, ["python", "Harness/bin/library", "eval-picks",
                                                         "Harness/tests/fixtures/library-picks.json"], 120, False, ())):
            with self.subTest(row.name):
                self.assertIn(row, self.tool.PLAN)

    def test_the_commit_guards_run_over_the_whole_tree_as_gates(self):
        # Nothing else runs them: sync.sh no longer commits and dev has no pre-commit hook.
        G = self.tool.GATE
        for row in (self.tool.Check("portability", G, [".claude/hooks/sync.sh", "--check-portability"], 60, False, ()),
                    self.tool.Check("no-secrets", G, [".claude/hooks/sync.sh", "--guard-secrets"], 60, False, ())):
            with self.subTest(row.name):
                self.assertIn(row, self.tool.PLAN)

    def test_every_row_has_its_own_name(self):
        names = [r.name for r in self.tool.PLAN]
        self.assertEqual(sorted(names), sorted(set(names)))

    def test_the_tools_that_stayed_behind_have_no_row(self):
        named = " ".join(r.name + " " + " ".join(r.argv) for r in self.tool.PLAN)
        for gone in ("brain", "mirror", "hindsight", "pcb-studio"):
            self.assertNotIn(gone, named)

    def test_the_start_check_verdict_is_a_detail(self):
        self.assertEqual(self.tool.detail_from("rows\nSTART COMPLETE — READY (1.20s)\nlater chatter\n", ""),
                         "START COMPLETE — READY (1.20s)")

    def test_a_failing_gate_fails_the_run_and_its_row_says_so(self):
        plan = [self.check("ok", self.tool.GATE, "print('fine')"),
                self.check("bad", self.tool.GATE, "import sys; print('broken here'); sys.exit(1)")]
        results, code = self.run_plan(plan)
        self.assertEqual(code, 1)
        self.assertEqual([(r.name, r.status) for r in results], [("ok", "pass"), ("bad", "FAIL")])
        self.assertEqual(results[1].detail, "broken here")

    def test_an_informational_row_never_fails_the_run(self):
        plan = [self.check("backlog", self.tool.INFO, "import sys; print('216 files, 86 with problems'); sys.exit(1)")]
        results, code = self.run_plan(plan)
        self.assertEqual(code, 0)
        self.assertEqual((results[0].status, results[0].detail), ("info", "216 files, 86 with problems"))

    def test_a_gate_that_outlives_its_bound_is_a_timeout_and_fails_the_run(self):
        plan = [self.check("hang", self.tool.GATE, "import time; time.sleep(30)", bound=1)]
        results, code = self.run_plan(plan)
        self.assertEqual((code, results[0].status), (1, "TIMEOUT"))
        self.assertLess(results[0].seconds, 10)

    def test_a_command_that_cannot_start_is_an_error_and_fails_the_run(self):
        plan = [self.tool.Check("missing", self.tool.GATE, [str(ROOT / "no-such-tool")], 5, False, ())]
        results, code = self.run_plan(plan)
        self.assertEqual((code, results[0].status), (1, "ERROR"))

    def test_a_timeout_retains_the_last_test_name_for_diagnosis(self):
        script = "import sys,time; print('test_slow (suite.Case) ...', file=sys.stderr, flush=True); time.sleep(30)"
        results, code = self.run_plan([self.check("suite", self.tool.GATE, script, bound=1)])
        self.assertEqual((code, results[0].status), (1, "TIMEOUT"))
        self.assertIn("test_slow (suite.Case)", results[0].detail)

    def test_fast_skips_the_slow_rows_and_judges_the_rest(self):
        plan = [self.check("slow-bad", self.tool.GATE, "import sys; sys.exit(1)", slow=True),
                self.check("quick", self.tool.GATE, "print('ok')")]
        results, code = self.run_plan(plan, fast=True)
        self.assertEqual(code, 0)
        self.assertEqual([r.status for r in results], ["SKIP", "pass"])
        results, code = self.run_plan(plan, fast=False)
        self.assertEqual((code, results[0].status), (1, "FAIL"))

    def test_only_runs_the_named_rows_and_refuses_an_unknown_name(self):
        plan = [self.check("a", self.tool.GATE, "print('a')"),
                self.check("b", self.tool.GATE, "import sys; sys.exit(1)")]
        results, code = self.run_plan(plan, only=["a"])
        self.assertEqual((code, [r.name for r in results]), (0, ["a"]))
        with self.assertRaises(self.tool.UsageError):
            self.run_plan(plan, only=["nope"])

    def test_naming_a_slow_row_runs_it_even_with_fast(self):
        # --fast is a default; --only is the caller saying which row they want,
        # and a SKIP for a row someone asked for reads as a pass.
        plan = [self.check("slow-bad", self.tool.GATE, "import sys; sys.exit(1)", slow=True)]
        results, code = self.run_plan(plan, fast=True, only=["slow-bad"])
        self.assertEqual((code, results[0].status), (1, "FAIL"))

    def test_a_tolerated_exit_code_is_informational_not_a_failure(self):
        # agent-memory check exits 2 where no memory folder exists, as on a device
        # that has not restored one; that is a note, not a broken checker.
        plan = [self.check("memory", self.tool.GATE, "import sys; print('no memory folder'); sys.exit(2)",
                           tolerate=(2,))]
        results, code = self.run_plan(plan)
        self.assertEqual((code, results[0].status, results[0].detail), (0, "info", "no memory folder"))

    def test_the_detail_is_the_verdict_even_when_a_test_prints_json_after_it(self):
        # unittest writes OK to stderr while a test under it prints JSON to stdout;
        # the table showed `}` for the whole Library tree until this was fixed. The
        # first assertion runs a whole check, so moving the call site out of
        # run_check fails here and not only in the unit assertions below it.
        plan = [self.check("tree", self.tool.GATE,
                           "import sys; print('{'); print('  \"sheets\": 6'); print('}');"
                           " print('Ran 228 tests in 106s', file=sys.stderr); print('OK', file=sys.stderr)")]
        results, _ = self.run_plan(plan)
        self.assertEqual(results[0].detail, "OK")
        self.assertEqual(self.tool.detail_from('{\n  "sheets": 6\n}', "Ran 228 tests in 106s\n\nOK\n"), "OK")
        self.assertEqual(self.tool.detail_from("57 checks, 0 failed\n", ""), "57 checks, 0 failed")
        self.assertEqual(self.tool.detail_from("", "FAILED (failures=2)\n"), "FAILED (failures=2)")
        self.assertEqual(self.tool.detail_from("chatter\nlast word\n", ""), "last word")
        self.assertEqual(self.tool.detail_from("", ""), "")

    def test_json_carries_every_row_and_the_exit_code(self):
        plan = [self.check("a", self.tool.GATE, "print('a')"),
                self.check("b", self.tool.INFO, "print('b')")]
        results, code = self.run_plan(plan)
        text = self.tool.as_json(results, code, ROOT, fast=False)
        data = json.loads(text)
        self.assertEqual(data["exit"], 0)
        self.assertEqual([r["name"] for r in data["results"]], ["a", "b"])
        self.assertEqual(set(data["results"][0]), {"name", "kind", "status", "seconds", "detail"})
        self.assertEqual(data["gates"], {"passed": 1, "failed": 0, "skipped": 0})

    def test_the_table_names_every_row_and_ends_with_a_verdict(self):
        plan = [self.check("first", self.tool.GATE, "print('one')"),
                self.check("second", self.tool.INFO, "print('two')")]
        results, code = self.run_plan(plan)
        table = self.tool.as_table(results, code)
        self.assertIn("first", table)
        self.assertIn("second", table)
        self.assertRegex(table.splitlines()[-1], r"^dev-check: 1 gate passed, 0 failed, 0 skipped, 1 informational")


class DailyTests(unittest.TestCase):
    """The 05:00 run on the Windows PC: owner decision 2026-09-24, from the grill's nine answers.

    A windowless start has no stdout, so the verdict must reach files; and a
    run that leaves none must read as an error, never as yesterday's pass.
    """

    @classmethod
    def setUpClass(cls):
        cls.tool = load()

    def setUp(self):
        import tempfile
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.folder, ignore_errors=True)
        self.now = __import__("datetime").datetime(2026, 9, 25, 5, 0)

    def results(self):
        R, gate = self.tool.Result, self.tool.GATE
        return [R("first", gate, "pass", 1.0, "OK"), R("second", gate, "FAIL", 2.0, "broken here")]

    def test_the_daily_run_writes_the_days_log_and_the_latest_verdict(self):
        self.tool.write_daily(self.results(), 1, self.folder, self.now)
        log = (self.folder / "2026-09-25.log").read_text(encoding="utf-8")
        self.assertIn("second", log)
        self.assertRegex(log.splitlines()[-1], r"^dev-check: 1 gate passed, 1 failed")
        latest = json.loads((self.folder / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual((latest["exit"], latest["failed"], latest["log"]), (1, ["second"], "2026-09-25.log"))
        self.assertEqual(latest["finished_at"], "2026-09-25T05:00")

    def test_only_the_newest_thirty_logs_stay(self):
        for day in range(1, 33):
            (self.folder / ("2026-08-%02d.log" % day if day <= 31 else "2026-09-01.log")).write_text("old")
        self.tool.write_daily(self.results(), 1, self.folder, self.now)
        logs = sorted(p.name for p in self.folder.glob("*.log"))
        self.assertEqual(len(logs), 30)
        self.assertEqual(logs[-1], "2026-09-25.log")
        self.assertNotIn("2026-08-01.log", logs)

    def test_a_run_that_leaves_no_verdict_is_an_error_not_a_pass(self):
        broken = subprocess.CompletedProcess([], 1, stdout="", stderr="Traceback: the checker died")
        with patch.object(self.tool.subprocess, "run", return_value=broken):
            code = self.tool.daily(self.folder, self.now)
        latest = json.loads((self.folder / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual((code, latest["exit"], latest["failed"]), (2, 2, ["dev-check"]))
        self.assertIn("the checker died", (self.folder / "2026-09-25.log").read_text(encoding="utf-8"))

    def test_the_real_run_is_the_console_python_with_no_window(self):
        calls = []
        def fake(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(
                {"exit": 0, "results": [{"name": "a", "kind": "gate", "status": "pass",
                                         "seconds": 1.0, "detail": "OK"}]}), stderr="")
        with patch.object(self.tool.subprocess, "run", side_effect=fake):
            self.assertEqual(self.tool.daily(self.folder, self.now), 0)
        argv, kwargs = calls[0]
        self.assertEqual(Path(argv[0]).name.lower(), "python.exe" if os.name == "nt" else Path(sys.executable).name)
        self.assertEqual(argv[-1], "--json")
        if os.name == "nt":
            self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)

    def test_the_task_runs_daily_at_five_windowless_and_never_wakes_the_pc(self):
        import xml.etree.ElementTree as ET
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        root = ET.fromstring(self.tool.daily_task_xml("C:/Python314/pythonw.exe", "C:/dev/Harness/bin/dev-check",
                                                      "PC\\owner").split("\n", 1)[1])
        text = lambda path: root.find(path, ns).text
        self.assertTrue(text("t:Triggers/t:CalendarTrigger/t:StartBoundary").endswith("T05:00:00"))
        self.assertEqual(text("t:Triggers/t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval"), "1")
        for setting, value in (("WakeToRun", "false"), ("StartWhenAvailable", "true"),
                               ("ExecutionTimeLimit", "PT45M"), ("MultipleInstancesPolicy", "IgnoreNew"),
                               ("DisallowStartIfOnBatteries", "false"), ("StopIfGoingOnBatteries", "false")):
            self.assertEqual(text("t:Settings/t:" + setting), value, setting)
        self.assertEqual(text("t:Principals/t:Principal/t:LogonType"), "InteractiveToken")
        self.assertEqual(text("t:Principals/t:Principal/t:RunLevel"), "LeastPrivilege")
        self.assertEqual(text("t:Actions/t:Exec/t:Command"), "C:/Python314/pythonw.exe")
        self.assertEqual(text("t:Actions/t:Exec/t:Arguments"), '"C:/dev/Harness/bin/dev-check" --daily')

    def test_the_mac_job_runs_daily_at_the_hour_with_a_path_that_outlives_the_session(self):
        import plistlib
        from pathlib import PurePosixPath
        # Path.home() itself, not HOME: Windows reads USERPROFILE, and this test runs on both.
        with patch.object(self.tool.Path, "home", return_value=PurePosixPath("/fixture-home/o")), \
                patch.dict(os.environ, PATH="/tmp/session-shims:/usr/bin"):
            job = plistlib.loads(self.tool.daily_plist("/usr/bin/python3", "/dev/Harness/bin/update-tools",
                                                       "DEVARNESS_update_daily", "apply --budget 1800", 4))
        self.assertEqual(job["Label"], "DEVARNESS_update_daily")
        self.assertEqual(job["ProgramArguments"],
                         ["/usr/bin/python3", "/dev/Harness/bin/update-tools", "apply", "--budget", "1800"])
        self.assertEqual(job["StartCalendarInterval"], {"Hour": 4, "Minute": 0})
        self.assertEqual(job["EnvironmentVariables"]["PATH"],
                         "/fixture-home/o/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")
        self.assertEqual(job["WorkingDirectory"], str(self.tool.ROOT))

    @unittest.skipUnless(sys.platform == "darwin", "launchd")
    def test_the_mac_install_and_removal_go_through_launchctl(self):
        calls = []
        fake = lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", "")
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, HOME=home), \
                patch.object(self.tool.subprocess, "run", side_effect=fake):
            job = Path(home) / "Harness" / "LaunchAgents" / "DEVARNESS_check_daily.plist"
            self.assertEqual(self.tool.schedule(True), 0)
            self.assertTrue(job.is_file())
            self.assertEqual(calls[-1][:2], ["launchctl", "bootstrap"])
            self.assertEqual(self.tool.schedule(False), 0)
            self.assertFalse(job.exists())
            self.assertEqual(calls[-1][:2], ["launchctl", "bootout"])

    def test_the_mac_update_job_is_written_and_loaded_on_either_device(self):
        # The same launchd path with the platform, uid, home and launchctl faked, so the
        # repositories rubric's criterion 7 ("no plist written") is caught on the Windows PC
        # too, now that update-tools installs its Mac job through this scheduler (2026-09-27).
        import plistlib
        calls = []
        fake = lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", "")
        with tempfile.TemporaryDirectory() as home, \
                patch.object(self.tool.sys, "platform", "darwin"), \
                patch.object(self.tool.os, "getuid", create=True, return_value=501), \
                patch.object(self.tool.Path, "home", return_value=Path(home)), \
                patch.object(self.tool.subprocess, "run", side_effect=fake), \
                patch("sys.stdout"):
            rc = self.tool.schedule(True, task="DEVARNESS_update_daily", tool="/dev/Harness/bin/update-tools",
                                    arguments="apply --budget 1800", hour=4)
            job = Path(home) / "Harness" / "LaunchAgents" / "DEVARNESS_update_daily.plist"
            self.assertEqual(rc, 0)
            self.assertTrue(job.is_file(), "no plist written")
            self.assertEqual(plistlib.loads(job.read_bytes())["Label"], "DEVARNESS_update_daily")
        self.assertEqual([argv[:2] for argv in calls], [["launchctl", "bootout"], ["launchctl", "bootstrap"]])


class RealPlanTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "the Windows search order")
    def test_child_python_discovers_git_bash_ahead_of_wsl(self):
        tool = load()
        expected = tool.bash()
        code = "import shutil; print(shutil.which('bash'))"
        check = tool.Check("child-shell", tool.GATE, py(code), 30, False, ())
        with patch.dict(os.environ, PATH=os.pathsep.join([
                str(Path(os.environ["SystemRoot"]) / "System32"),
                str(Path(expected).parent.parent / "cmd")])):
            result = tool.run_check(check, ROOT)
        self.assertEqual(Path(result.detail), Path(expected))

    def test_every_command_in_the_real_plan_names_a_file_that_exists(self):
        tool = load()
        for check in tool.PLAN:
            with self.subTest(check.name):
                argv = tool.command_for(check, ROOT)
                self.assertTrue(Path(argv[0]).exists() or argv[0] in ("bash", sys.executable), argv)
                script = next((a for a in argv[1:] if not a.startswith("-") and (ROOT / a).exists()), None)
                self.assertIsNotNone(script, "no runnable path in " + " ".join(argv))

    def test_no_test_file_in_the_workspace_is_left_out_of_the_plan(self):
        # The plan names the .claude/hooks suites one by one, and a list kept by
        # hand drifts: the launcher list, .gitattributes and the clone excludes
        # each went stale that way. Harness/tests is covered by the discover row.
        tool = load()
        named = " ".join(" ".join(c.argv) for c in tool.PLAN)
        missing = [p.as_posix() for p in sorted((ROOT / ".claude" / "hooks").glob("test_*.py"))
                   if p.relative_to(ROOT).as_posix() not in named]
        self.assertEqual(missing, [], "add to dev-check's PLAN: " + ", ".join(missing))
        discovered = [c for c in tool.PLAN if "discover" in c.argv]
        self.assertTrue(discovered, "nothing runs the Harness/tests tree")

    def test_a_python_launcher_runs_under_this_python_and_a_bash_one_under_bash(self):
        tool = load()
        by_name = {c.name: c for c in tool.PLAN}
        self.assertEqual(tool.command_for(by_name["agent-memory-check"], ROOT)[0], sys.executable)
        bash = tool.command_for(by_name["i18n-check"], ROOT)[0]
        if os.name == "nt":
            self.assertEqual(Path(bash).name.lower(), "bash.exe")
        else:
            self.assertEqual(bash, "bash")

    @unittest.skipUnless(os.name == "nt", "the Windows search order")
    def test_windows_runs_a_bash_launcher_under_git_bash_never_the_wsl_launcher(self):
        # A bare "bash" is found in System32 first, WSL's launcher; its bash
        # stripped the backslashes from the launcher's path, and three rows
        # failed with "No such file" for a launcher path stripped of them (2026-09-19).
        tool = load()
        bash = Path(tool.command_for({c.name: c for c in tool.PLAN}["i18n-check"], ROOT)[0])
        self.assertTrue(bash.is_file(), bash)
        self.assertNotIn("system32", str(bash).lower())
        self.assertTrue((bash.parent.parent / "cmd" / "git.exe").is_file()
                        or (bash.parent / "git.exe").is_file(), "not Git for Windows' bash: " + str(bash))

    def test_cli_fast_skips_a_failing_slow_gate_but_only_runs_it(self):
        tool = load()
        self.assertGreaterEqual(sum(check.slow for check in tool.PLAN), 3,
                                "the real plan must keep its slow suites out of --fast")
        plan = [tool.Check("quick", tool.GATE, py("print('ready')"), 30, False, ()),
                tool.Check("slow", tool.GATE, py("raise SystemExit(1)"), 30, True, ())]
        cases = [(["--fast", "--json"], 0, ["pass", "SKIP"]),
                 (["--fast", "--only", "slow", "--json"], 1, ["FAIL"])]
        for argv, expected_code, statuses in cases:
            with self.subTest(argv=argv), patch.object(tool, "PLAN", plan):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = tool.main(argv)
                data = json.loads(output.getvalue())
                self.assertEqual(code, expected_code)
                self.assertEqual(data["exit"], expected_code)
                self.assertEqual([row["status"] for row in data["results"]], statuses)


if __name__ == "__main__":
    unittest.main()
