#!/usr/bin/env python3
"""laya-service: dev's short decisions through laya, trusted only above a measured threshold.

Run: python3 Library/tests/test_laya_service.py

The owner, 2026-09-24: "whenever it takes short decision and need no
hallucination, laya is to help", and laya must be running "no matter how".
These tests cover the parts that need no model: the questions, the
threshold, the fallback order, the service task and the evaluation set.
"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "Library" / "bin" / "laya-service"
EVAL = ROOT / "Library" / "laya-eval" / "decisions.jsonl"
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def load():
    loader = importlib.machinery.SourceFileLoader("laya_service", str(TOOL))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("laya_service", loader))
    loader.exec_module(module)
    return module


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()

    def test_only_the_decisions_that_clear_the_gate_are_offered(self):
        for kind in ("failure", "change"):
            self.assertEqual(self.mod.questions_for(kind)["q"]["type"], "noul")
        # Routing scored 14 of 38 on the evaluation set (2026-09-24): measured, never offered.
        with self.assertRaises(ValueError):
            self.mod.questions_for("route")
        self.assertEqual(self.mod.MEASURED["route"]["q"]["type"], "choice")
        with self.assertRaises(ValueError):
            self.mod.questions_for("weather")

    def test_an_answer_below_the_threshold_is_not_trusted(self):
        result = {"answers": {
            "weak": {"type": "noul", "noul": 0.74, "confidence": 0.74},
            "yes": {"type": "noul", "noul": 0.93, "confidence": 0.93},
            "no": {"type": "noul", "noul": 0.04, "confidence": 0.96},
            "pick": {"type": "choice", "choice": "md-format", "confidence": 0.85}}}
        answers = self.mod.mark(result)["answers"]
        self.assertFalse(answers["weak"]["trusted"])
        self.assertEqual((answers["yes"]["answer"], answers["yes"]["trusted"]), ("yes", True))
        self.assertEqual((answers["no"]["answer"], answers["no"]["trusted"]), ("no", True))
        self.assertEqual((answers["pick"]["answer"], answers["pick"]["trusted"]), ("md-format", True))

    def test_decide_returns_one_labelled_answer(self):
        seen = {}

        def predict(state, questions):
            seen.update(state=state, questions=questions)
            return {"answers": {"q": {"type": "noul", "noul": 0.1, "confidence": 0.9}}}, "service"
        verdict = self.mod.decide("failure", "Ran 12 tests\nOK", ask=predict)
        self.assertEqual(seen["state"], {"text": "Ran 12 tests\nOK"})
        self.assertEqual(verdict, {"kind": "failure", "answer": "no", "confidence": 0.9,
                                   "trusted": True, "source": "service"})

    def test_the_gate_counts_only_the_offered_decisions(self):
        rows = {"failure": [(True, True)] * 19 + [(False, True)], "change": [(True, True)] * 20,
                "route": [(False, True)] * 30}
        self.assertTrue(self.mod.passes(rows))
        rows["change"] = [(False, True)] * 5 + [(True, True)] * 15
        self.assertFalse(self.mod.passes(rows))


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.calls = []

    def post_after(self, failures):
        def post(state, questions, model):
            self.calls.append("post")
            if self.calls.count("post") <= failures:
                raise OSError("connection refused")
            return {"answers": {}}
        return post

    def local(self, state, questions, model):
        self.calls.append("local")
        return {"answers": {}}

    def start(self):
        self.calls.append("start")
        return True

    def test_a_running_service_answers(self):
        _, source = self.mod.predict({}, {}, post=self.post_after(0), start=self.start, local=self.local)
        self.assertEqual((source, self.calls), ("service", ["post"]))

    def test_a_down_service_is_started_and_asked_again(self):
        _, source = self.mod.predict({}, {}, post=self.post_after(1), start=self.start, local=self.local)
        self.assertEqual((source, self.calls), ("service", ["post", "start", "post"]))

    def test_when_the_service_cannot_run_the_call_runs_in_process(self):
        _, source = self.mod.predict({}, {}, post=self.post_after(9), start=self.start, local=self.local)
        self.assertEqual((source, self.calls), ("in-process", ["post", "start", "post", "local"]))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()

    def test_the_service_answers_only_on_this_machine(self):
        self.assertEqual(self.mod.SERVICE_ENV["LAYA_HOST"], "127.0.0.1")

    def test_the_task_starts_at_logon_restarts_on_failure_and_never_stops(self):
        root = ET.fromstring(self.mod.service_xml("pythonw.exe", "C:/dev/Library/bin/laya-service", "PC\\owner").split("\n", 1)[1])
        text = lambda path: root.find(path, NS).text
        self.assertIsNotNone(root.find("t:Triggers/t:LogonTrigger", NS))
        self.assertEqual(text("t:Settings/t:ExecutionTimeLimit"), "PT0S")
        self.assertEqual(text("t:Settings/t:RestartOnFailure/t:Interval"), "PT1M")
        for setting, value in (("DisallowStartIfOnBatteries", "false"), ("StopIfGoingOnBatteries", "false"),
                               ("MultipleInstancesPolicy", "IgnoreNew")):
            self.assertEqual(text("t:Settings/t:" + setting), value, setting)
        self.assertEqual(text("t:Actions/t:Exec/t:Arguments"), '"C:/dev/Library/bin/laya-service" serve')


class RoutingDefaultTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()

    def test_local_fallback_keeps_english_when_upstream_default_changes(self):
        # No model weights: this boundary double has the new upstream default.
        def router(device, default="multilingual"):
            return SimpleNamespace(predict=lambda state, questions: {"model": default})

        with mock.patch.dict(sys.modules, {"laya": SimpleNamespace(Router=router)}):
            with mock.patch.dict(os.environ, {}, clear=True):
                result = self.mod.run_local({"text": "OK (skipped=4)"}, {}, "auto")
        self.assertEqual(result["model"], "english")

    def test_service_keeps_english_when_upstream_default_changes(self):
        served = {}

        def serve():
            served["model"] = os.environ.get("LAYA_DEFAULT_MODEL", "multilingual")

        with mock.patch.dict(sys.modules, {"laya.serve": SimpleNamespace(main=serve)}):
            with mock.patch.dict(os.environ, {}, clear=True):
                self.mod.serve_http()
        self.assertEqual(served["model"], "english")


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()

    def test_scoring_counts_precision_only_where_the_answer_is_trusted(self):
        rows = [(True, True), (True, True), (False, False), (True, False), (False, True)]
        # (right, trusted): three trusted answers, two of them right
        self.assertEqual(self.mod.score(rows), {"items": 5, "right": 3, "answered": 3,
                                                "trusted_right": 2, "precision": 0.667, "coverage": 0.6})

    def test_the_evaluation_set_is_labelled_for_every_kind(self):
        rows = [json.loads(line) for line in EVAL.read_text(encoding="utf-8").splitlines() if line.strip()]
        owners = set(self.mod.OWNERS)
        for row in rows:
            self.assertIn(row["kind"], ("failure", "change", "route"), row)
            valid = owners if row["kind"] == "route" else {"yes", "no"}
            self.assertIn(row["answer"], valid, row)
            self.assertTrue(row["text"].strip(), row)
        for kind in ("failure", "change", "route"):
            self.assertGreaterEqual(sum(r["kind"] == kind for r in rows), 30, kind)
        self.assertEqual(len({r["text"] for r in rows}), len(rows), "a duplicated item")


PYTHONW = Path(sys.executable).with_name("pythonw.exe")


@unittest.skipUnless(PYTHONW.is_file() and (ROOT / "Library/.runtime/laya/.venv/Scripts/python.exe").is_file(),
                     "needs Windows' pythonw and laya's runtime")
class WindowlessParentTests(unittest.TestCase):
    def test_a_windowless_parent_still_gets_the_servers_answer(self):
        # update-tools's 04:00 task runs under pythonw, and setup-laya's check
        # starts laya-service from there. On 2026-09-25 the relaunch into laya's
        # runtime took a new console instead of the pipes, and initialize gave
        # no answer in 120 s, twice.
        ask = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "test", "version": "1"}}}
        server = subprocess.Popen([str(PYTHONW), str(TOOL)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        try:
            out, _ = server.communicate(json.dumps(ask) + "\n", timeout=90)
        except subprocess.TimeoutExpired:
            # The whole tree: a relaunched child that kept the pipes would
            # otherwise hold communicate() open for ever.
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(server.pid)], capture_output=True)
            server.communicate()
            self.fail("laya-service under pythonw gave no answer in 90 s")
        replies = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
        self.assertIn(1, [r.get("id") for r in replies], out[-300:])


if __name__ == "__main__":
    unittest.main()
