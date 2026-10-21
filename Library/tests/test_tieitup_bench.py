"""TieItUp's benchmark runner: spend stop, clean-up, plugin, summary maths, probe, selftest.

Run as `python -B Library/tests/test_tieitup_bench.py`. No test starts a model session:
the cells are stubs and the CLI is never called.
"""
import importlib.util, io, json, os, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

bench = _load("tieitup_bench", ROOT / "Library/tieitup-bench.py")
QUICK9 = ["scope-recipients", "conv-seam", "csv-sum", "critic-email", "auth-token", "reuse-slug",
          "vibe-todo", "vibe-shortener", "open-decorators"]
HIDDEN6 = QUICK9[:6]
TIE = ["tie-save-json", "tie-py39", "tie-errors"]

def cell(task, arm, loc=10, cost=0.1, ok=True, run=0, **extra):
    return {"task": task, "arm": arm, "model": "opus", "run": run, "correct": int(ok), "safe": int(ok),
            "total_loc": loc, "cost": cost, **extra}

def pilot(p2_loc, p2_fail=()):
    """One cell per task and arm; ponytail2's LOC per quick task from p2_loc."""
    rows = []
    for i, t in enumerate(QUICK9 + TIE):
        rows.append(cell(t, "ponytail", loc=10))
        rows.append(cell(t, "ponytail2", loc=p2_loc[i] if i < 9 else 10, ok=t not in p2_fail))
    return rows

class SpendStop(unittest.TestCase):
    def test_stops_at_80_percent_and_lists_unrun(self):
        cells = [("t", "ponytail", r) for r in range(6)]
        out = bench.run_cells(cells, lambda c: {"task": c[0], "arm": c[1], "run": c[2], "cost": 3.0},
                              stop_usd=10 * bench.STOP_SHARE, workers=1)
        self.assertEqual(len(out["results"]), 3)          # 0, 3, 6 are under $8; 9 is not
        self.assertEqual(out["unrun"], cells[3:])
        self.assertIn("stop line", out["stop"])

    def test_usage_limit_stops_and_is_not_a_score(self):
        cells = [("t", "a", r) for r in range(4)]
        def one(c):
            return {"task": "t", "arm": "a", "run": c[2], "cost": 0.1,
                    **({"infra": "usage-limit"} if c[2] == 1 else {})}
        out = bench.run_cells(cells, one, stop_usd=100, workers=1)
        self.assertEqual(len(out["results"]), 2)
        self.assertEqual(out["unrun"], cells[2:])
        self.assertIn("usage-limit", out["stop"])

    def test_runner_exception_is_a_crash_not_a_score(self):
        def one(c):
            if c[2] == 0: raise PermissionError("folder busy")
            return {"task": "t", "arm": "a", "run": c[2], "cost": 0.1, "correct": 1, "safe": 1}
        out = bench.run_cells([("t", "a", 0), ("t", "a", 1)], one, stop_usd=100, workers=1)
        self.assertEqual([r.get("infra") for r in out["results"]], ["crash", None])
        self.assertIsNone(out["stop"])

    def test_run_refuses_without_budget(self):
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            bench.main(["run"])

class Auto(unittest.TestCase):
    """The automatic pilot runs on a harness move, within its cap, and never on a model the runner does not expect."""
    DATE = __import__("datetime").date

    def drift(self, version=None, model=None):
        return {"bench": {"date": "2026-10-15", "claude": "2.1.292 (Claude Code)", "model": bench.OPUS},
                "version": version, "model": model}

    def test_decisions(self):
        today = self.DATE(2026, 11, 1)
        self.assertFalse(bench.auto_decision(None, None, today)[0])
        self.assertFalse(bench.auto_decision(self.drift(), None, today)[0])
        go, why = bench.auto_decision(self.drift(version=("2.1.292", "2.2.0")), self.DATE(2026, 10, 15), today)
        self.assertTrue(go, why)
        self.assertIn("$%.2f" % bench.AUTO_BUDGET, why)
        go, why = bench.auto_decision(self.drift(version=("2.1.292", "2.2.0")), self.DATE(2026, 10, 28), today)
        self.assertFalse(go)
        self.assertIn("2026-11-04", why)
        go, why = bench.auto_decision(self.drift(model=(bench.OPUS, "claude-opus-9")), None, today)
        self.assertFalse(go)
        self.assertIn("OPUS", why)
        self.assertTrue(bench.auto_decision(self.drift(model=("claude-opus-5-4", bench.OPUS)), None, today)[0])

    def test_drift_comes_from_the_live_command(self):
        with mock.patch("subprocess.run", side_effect=OSError("no claude in tests")):
            drift = bench.harness_drift()
        self.assertTrue(drift is None or set(drift) == {"bench", "version", "model"}, drift)

    def test_auto_records_the_attempt_then_runs_the_pilot(self):
        calls = []
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(bench, "RUNTIME", Path(d)), \
                mock.patch.object(bench, "EVIDENCE", Path(d) / "evidence"), \
                mock.patch.object(bench, "harness_drift", lambda: self.drift(version=("2.1.292", "2.2.0"))), \
                mock.patch.object(bench, "run_bench", lambda run, compare, budget, runs: calls.append((budget, runs)) or 0), \
                mock.patch.object(bench, "selftest", lambda: []), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(bench.auto(None, None, self.DATE(2026, 11, 1)), 0)
            self.assertEqual(calls, [(bench.AUTO_BUDGET, 1)])
            self.assertEqual(json.loads((Path(d) / "bench" / "auto.json").read_text())["last"], "2026-11-01")
            bench.auto(None, None, self.DATE(2026, 11, 3))
            self.assertEqual(len(calls), 1)

class Infrastructure(unittest.TestCase):
    def ws(self, claude=None, stderr=""):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        if claude is not None: (d / "_claude.json").write_text(json.dumps(claude), encoding="utf-8")
        (d / "_claude.stderr.txt").write_text(stderr, encoding="utf-8")
        return d

    def test_classify(self):
        self.assertIsNone(bench.classify(self.ws({"result": "done", "total_cost_usd": 0.1}), {}))
        self.assertEqual(bench.classify(self.ws({"is_error": True, "result": "Claude usage limit reached"}), {}),
                         "usage-limit")
        self.assertEqual(bench.classify(self.ws({"result": "x"}, "[KILLED after 300s timeout]"), {}), "timeout")
        self.assertEqual(bench.classify(self.ws(None), {}), "crash")
        self.assertEqual(bench.classify(self.ws({"error": "boom"}), {}), "crash")
        self.assertEqual(bench.classify(self.ws({"result": "x"}), {"error": "boom"}), "crash")

    def test_served_models_from_transcript(self):
        d = self.ws()
        t = d / "s.jsonl"
        t.write_text("\n".join(json.dumps(r) for r in [
            {"type": "user", "message": {"content": "hi"}},
            {"type": "assistant", "message": {"model": "claude-opus-5-5"}},
            {"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001"}}]) + "\nnot json\n",
            encoding="utf-8")
        self.assertEqual(bench.served_models(t), {"claude-opus-5-5", "claude-haiku-4-5-20251001"})
        self.assertFalse(bench.served_by_opus(bench.served_models(t)))
        self.assertTrue(bench.served_by_opus({"claude-opus-5-5"}))
        self.assertFalse(bench.served_by_opus(set()))

class CleanUp(unittest.TestCase):
    def test_removes_only_what_the_run_created(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            config, home, appdata = d / "claude", d / "home", d / "appdata"
            (config / "projects").mkdir(parents=True)
            (config / "settings.json").write_text("{}", encoding="utf-8")
            (config / ".ponytail-old").write_text("kept", encoding="utf-8")
            targets = bench.cleanup_targets(config, home, appdata)
            before = bench.snapshot(targets)
            (config / ".ponytail-active").write_text("full", encoding="utf-8")
            (config / "ponytail-statusline.ps1").write_text("x", encoding="utf-8")
            (config / "ponytail-modes").mkdir()
            (config / "ponytail-modes" / "abc").write_text("full", encoding="utf-8")
            (config / "something-new").write_text("x", encoding="utf-8")
            (home / ".config" / "ponytail").mkdir(parents=True)
            (home / ".config" / "ponytail" / "config.json").write_text("{}", encoding="utf-8")
            (appdata / "ponytail").mkdir(parents=True)
            removed, left = bench.clean_up(before)
            self.assertEqual(sorted(p.name for p in config.iterdir()),
                             [".ponytail-old", "projects", "settings.json", "something-new"])
            self.assertFalse((home / ".config" / "ponytail").exists())
            self.assertTrue((home / ".config").exists())
            self.assertFalse((appdata / "ponytail").exists())
            self.assertIn(str(config / "something-new"), left)
            self.assertEqual(len(removed), 5)

    def test_existing_mode_folder_keeps_its_old_entries(self):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "claude"
            (config / "ponytail-modes").mkdir(parents=True)
            (config / "ponytail-modes" / "old").write_text("x", encoding="utf-8")
            before = bench.snapshot(bench.cleanup_targets(config, Path(d), Path(d)))
            (config / "ponytail-modes" / "new").write_text("x", encoding="utf-8")
            bench.clean_up(before)
            self.assertEqual([p.name for p in (config / "ponytail-modes").iterdir()], ["old"])

class Plugin(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.sources = []
        for name, text in (("ponytail.md", "PONYTAIL RULES"), ("SKILL.md", "TIEITUP SKILL"),
                           ("python.md", "PYTHON PACK")):
            p = self.tmp / name
            p.write_text(text, encoding="utf-8")
            self.sources.append(p)
        self.tieitup = self.tmp / "fake-tieitup"
        self.tieitup.write_text("import sys\nprint(sys.argv[-1] + ':1 [open-file abc12345] no encoding (rule 6)')\n",
                                encoding="utf-8")
        self.plugin = bench.build_plugin(self.tmp / "plugin", self.sources, sys.executable, self.tieitup)

    def hook(self, script, event):
        out = subprocess.run([sys.executable, "-B", str(self.plugin / "hooks" / script)], input=json.dumps(event),
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout) if out.stdout.strip() else None

    def test_shape(self):
        manifest = json.loads((self.plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "ponytail2")
        hooks = json.loads((self.plugin / manifest["hooks"]).read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(sorted(hooks), ["PostToolUse", "SessionStart"])
        self.assertEqual(hooks["PostToolUse"][0]["matcher"], "Edit|Write|MultiEdit")
        for event in hooks.values():
            command = event[0]["hooks"][0]["command"]
            self.assertIn(Path(sys.executable).as_posix(), command)
            self.assertNotIn("\\", command)

    def test_session_start_injects_all_three(self):
        ctx = self.hook("session_start.py", {"hook_event_name": "SessionStart"})["hookSpecificOutput"]
        self.assertEqual(ctx["hookEventName"], "SessionStart")
        for text in ("PONYTAIL RULES", "TIEITUP SKILL", "PYTHON PACK"):
            self.assertIn(text, ctx["additionalContext"])

    def test_post_edit_runs_check_and_logs(self):
        work = self.tmp / "cell"
        work.mkdir()
        target = work / "a.py"
        target.write_text("x = 1\n", encoding="utf-8")
        out = self.hook("post_edit.py", {"cwd": str(work), "tool_name": "Write",
                                         "tool_input": {"file_path": str(target)}})
        self.assertIn("[open-file abc12345]", out["hookSpecificOutput"]["additionalContext"])
        log = [json.loads(l) for l in (work / bench.HOOK_LOG).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(log, [{"file": str(target), "findings": 1, "exit": 0}])

    def test_missing_source_is_refused(self):
        with self.assertRaises(SystemExit):
            bench.build_plugin(self.tmp / "p2", [self.tmp / "absent.md"], sys.executable, self.tieitup)

class Summary(unittest.TestCase):
    def setUp(self):
        _, self.compare = bench.harness()

    def summary(self, rows, runs=1):
        return bench.summarise(rows, self.compare, QUICK9, HIDDEN6, TIE, runs)

    def test_eight_of_nine_claims_better(self):
        s = self.summary(pilot([5] * 8 + [12]))
        self.assertEqual((s["loc"]["wins"], s["loc"]["losses"]), (8, 1))
        self.assertLess(s["loc"]["p"], 0.05)
        self.assertTrue(s["loc"]["better"])
        self.assertIn("better", s["headline"])

    def test_seven_of_nine_is_within_noise(self):
        s = self.summary(pilot([5] * 7 + [12, 12]))
        self.assertFalse(s["loc"]["better"])
        self.assertIn("within noise", s["headline"])

    def test_crashed_cell_is_infrastructure_not_zero(self):
        rows = pilot([5] * 9)
        rows = [r for r in rows if not (r["task"] == "csv-sum" and r["arm"] == "ponytail2")]
        rows.append({"task": "csv-sum", "arm": "ponytail2", "model": "opus", "run": 0, "error": "boom",
                     "infra": "crash"})
        s = self.summary(rows)
        self.assertEqual(s["infrastructure"], [{"task": "csv-sum", "arm": "ponytail2", "run": 0, "kind": "crash"}])
        self.assertEqual(s["quality"]["ponytail2_fails_ponytail_passes"], [])
        self.assertEqual(s["loc"]["wins"], 8)                     # the crashed task has no pair
        self.assertFalse(s["regression"])

    def test_pilot_regression_is_two_of_six(self):
        self.assertFalse(self.summary(pilot([10] * 9, p2_fail=HIDDEN6[:1]))["regression"])
        s = self.summary(pilot([10] * 9, p2_fail=HIDDEN6[:2]))
        self.assertTrue(s["regression"])
        self.assertIn("REGRESSION", s["headline"])
        self.assertFalse(self.summary(pilot([10] * 9, p2_fail=("vibe-todo", "vibe-shortener")))["regression"])

    def test_measurement_regression(self):
        def three(fails_by_task):
            rows = []
            for t in QUICK9:
                for r in range(3):
                    rows.append(cell(t, "ponytail", run=r))
                    rows.append(cell(t, "ponytail2", run=r, ok=r >= fails_by_task.get(t, 0)))
            return rows
        self.assertFalse(self.summary(three({"csv-sum": 1, "conv-seam": 1}), runs=3)["regression"])
        self.assertTrue(self.summary(three({"csv-sum": 2}), runs=3)["regression"])

    def test_tieitup_tasks_reported_per_task_never_pooled(self):
        s = self.summary(pilot([10] * 9, p2_fail=("tie-py39",)))
        self.assertEqual(sorted(s["tieitup_tasks"]), sorted(TIE))
        self.assertEqual(s["tieitup_tasks"]["tie-py39"]["ponytail2"]["passed"], 0)
        self.assertEqual(s["loc"]["tasks"], 9)
        self.assertNotIn("tie-py39", json.dumps(s["quality"]))

    def test_cost_sign_test_reported(self):
        rows = pilot([10] * 9)
        for r in rows:
            if r["arm"] == "ponytail2" and r["task"] in QUICK9: r["cost"] = 0.2
        s = self.summary(rows)
        self.assertEqual((s["cost"]["wins"], s["cost"]["losses"]), (0, 9))
        self.assertTrue(s["cost"]["significant_rise"])

    def test_evidence_written_only_when_complete(self):
        with tempfile.TemporaryDirectory() as d:
            run_dir, evidence = Path(d) / "run", Path(d) / "evidence"
            run_dir.mkdir()
            self.assertIsNone(bench.write_summary({"date": "2026-10-15"}, run_dir, evidence, complete=False))
            self.assertFalse(evidence.exists())
            path = bench.write_summary({"date": "2026-10-15"}, run_dir, evidence, complete=True)
            self.assertEqual(path, evidence / "bench-2026-10-15.json")
            self.assertTrue((run_dir / "summary.json").exists())

class Probe(unittest.TestCase):
    """Fixture records: the parser is not checked against a real stream-json record."""
    DEV = {"grill-first", "ponytail", "tieitup"}

    def stream(self, **init):
        record = {"type": "system", "subtype": "init", "model": "claude-opus-5-5",
                  "plugins": [{"name": "ponytail2", "path": "/x"}], "skills": ["ponytail2:helper"], **init}
        return "\n".join([json.dumps({"type": "system", "subtype": "hook_started"}), json.dumps(record),
                          json.dumps({"type": "result", "result": "ok"})])

    def test_clean_probe(self):
        ok, problems, _ = bench.parse_probe(self.stream(), "ponytail2", self.DEV)
        self.assertTrue(ok, problems)

    def test_leaks_fail(self):
        for init in ({"plugins": [{"name": "ponytail2"}, {"name": "superpowers"}]},
                     {"skills": ["ponytail2:helper", "grill-first"]},
                     {"skills": ["ponytail"]},
                     {"model": "claude-sonnet-5-5"}):
            ok, problems, _ = bench.parse_probe(self.stream(**init), "ponytail2", self.DEV)
            self.assertFalse(ok, init)
            self.assertTrue(problems)

    def test_claude_codes_builtin_plugins_load_in_both_arms_and_pass(self):
        builtin = {"name": "cc-plugin-telemetry", "path": "builtin", "source": "cc-plugin-telemetry@builtin"}
        ok, problems, _ = bench.parse_probe(self.stream(plugins=[{"name": "ponytail2", "path": "/x"}, builtin]),
                                            "ponytail2", self.DEV)
        self.assertTrue(ok, problems)

    def test_every_session_turns_off_the_dev_skills_in_memory(self):
        run, _ = bench.harness()
        original = run._base_cmd
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "isolation.json"
            try:
                bench.isolate(run, {"grill-first", "tieitup"}, path)
                bench.isolate(run, {"grill-first", "tieitup"}, path)
                cmd = run._base_cmd("claude", "p", "opus")
                self.assertEqual(cmd.count("--settings"), 1)
                self.assertEqual(cmd[cmd.index("--settings") + 1], str(path))
                self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                                 {"skillOverrides": {"grill-first": "off", "tieitup": "off"}})
            finally:
                run._base_cmd = original

    def test_record_that_cannot_show_is_failed(self):
        self.assertFalse(bench.parse_probe('{"type": "result"}\n', "ponytail", self.DEV)[0])
        bare = json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5-5"})
        self.assertFalse(bench.parse_probe(bare, "ponytail", self.DEV)[0])

    def test_probe_command_uses_stream_json(self):
        run, _ = bench.harness()
        cmd = bench.probe_command(run, "claude", "ponytail", "/plugin")
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "stream-json")
        self.assertIn("--verbose", cmd)
        self.assertEqual(cmd[cmd.index("--plugin-dir") + 1], "/plugin")
        self.assertIn("Reply with: ok", cmd)

class Windows(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "CREATE_NO_WINDOW is Windows-only")
    def test_every_popen_gets_create_no_window(self):
        original = subprocess.Popen
        try:
            bench.no_windows()
            bench.no_windows()                             # twice must not stack
            seen = {}
            def record(self, *a, **kw): seen.update(kw); raise OSError("stop here")
            with mock.patch.object(original, "__init__", record):
                with self.assertRaises(OSError): subprocess.run(["x"])
            self.assertTrue(seen["creationflags"] & subprocess.CREATE_NO_WINDOW)
        finally:
            subprocess.Popen = original

class SelfTest(unittest.TestCase):
    def quiet(self):
        buf = io.StringIO()
        with redirect_stdout(buf): failures = bench.selftest()
        return failures, buf.getvalue()

    def test_selftest_passes_with_tieitup_tasks(self):
        failures, out = self.quiet()
        self.assertEqual(failures, 0, out)
        for t in TIE:
            self.assertIn(f"ok  {t:12} good", out)
            self.assertIn(f"ok  {t:12} bad", out)
        self.assertIn("ok  infrastructure", out)

    def test_broken_reference_fails_selftest(self):
        run, _ = bench.harness()
        for t in TIE:
            task = run.TASKS[t]
            good = task["good"]
            try:
                task["good"] = task["bad"]
                failures, _ = self.quiet()
                self.assertGreater(failures, 0, t)
            finally:
                task["good"] = good

    def test_harness_tasks_stay_in_memory(self):
        run, _ = bench.harness()
        self.assertTrue(set(TIE) <= set(run.TASKS))
        tasks_file = ROOT / "Library/ponytail/benchmarks/agentic/tasks.py"
        self.assertNotIn("tie-save-json", tasks_file.read_text(encoding="utf-8"))
        self.assertEqual(bench.quick_tasks(run), QUICK9)
        self.assertEqual(bench.hidden_tasks(run), HIDDEN6)

class Graders(unittest.TestCase):
    """Aster's review of the three tasks (2026-10-15): each grades only what its prompt asks."""

    def grade(self, task, files):
        run, _ = bench.harness()
        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                Path(d, name).write_text(text, encoding="utf-8")
            return run.TASKS[task]["score"](d)

    def test_a_corrupt_orders_file_must_raise_but_need_not_name_the_file(self):
        plain = ("import json, os\n\ndef load_orders(path):\n    if not os.path.exists(path):\n"
                 "        return []\n    with open(path, encoding='utf-8') as f:\n        return json.load(f)\n")
        self.assertEqual(self.grade("tie-errors", {"orders.py": plain})["safe"], 1)

    def test_files_left_by_a_failed_save_are_caught(self):
        litter = ("import json, os\n\ndef save_settings(path, settings):\n"
                  "    tmp = path + '.tmp'\n    with open(tmp, 'w', encoding='utf-8') as f:\n"
                  "        json.dump(settings, f)\n    os.replace(tmp, path)\n")
        result = self.grade("tie-save-json", {"settings_store.py": litter})
        self.assertEqual(result["safe"], 0, result)
        self.assertIn("left files behind", result["reason"])

    def test_only_the_requested_file_is_held_to_python_39(self):
        good = ("def write_report(path, lines):\n    with open(path, 'w', encoding='utf-8', newline='\\n') as f:\n"
                "        f.write(''.join(line + '\\n' for line in lines))\n")
        helper = "def pairs(a, b):\n    return list(zip(a, b, strict=True))\n"
        self.assertEqual(self.grade("tie-py39", {"report.py": good, "scratch_tool.py": helper})["safe"], 1)

    def test_produced_code_that_exits_or_hangs_is_a_failed_cell(self):
        run, _ = bench.harness()
        tasks = run.TASKS["tie-errors"]["score"].__globals__
        for name, body in (("exits", "raise SystemExit(3)\n"), ("hangs", "while True:\n    pass\n")):
            with self.subTest(name), mock.patch.dict(tasks, GRADE_SECONDS=3):
                result = self.grade("tie-errors", {"orders.py": body})
                self.assertEqual((result["correct"], result["safe"]), (0, 0), result)


if __name__ == "__main__":
    unittest.main()
