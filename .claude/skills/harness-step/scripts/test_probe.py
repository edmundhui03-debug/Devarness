"""probe.summarize reads a stream-json trajectory into the numbers a harness step compares."""

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402


def event(kind, **fields):
    return json.dumps(dict(type=kind, **fields))


def tool_use(name):
    return event("assistant", message={"content": [{"type": "tool_use", "name": name, "input": {}}]})


def tool_result(error):
    return event("user", message={"content": [{"type": "tool_result", "is_error": error, "content": "x"}]})


RESULT_OK = event("result", subtype="success", is_error=False, num_turns=4, total_cost_usd=0.5,
                  duration_ms=61000, result="done",
                  usage={"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 300,
                         "cache_creation_input_tokens": 70})


class SummarizeTests(unittest.TestCase):
    def summarize(self, *lines):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run.jsonl"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return probe.summarize(path)

    def test_counts_tools_errors_and_usage(self):
        s = self.summarize(tool_use("Read"), tool_result(False), tool_use("Read"), tool_use("Bash"),
                           tool_result(True), RESULT_OK)
        self.assertTrue(s["delivered"])
        self.assertEqual(s["tools"], {"Read": 2, "Bash": 1})
        self.assertEqual((s["tool_calls"], s["tool_errors"]), (3, 1))
        self.assertEqual((s["tokens"], s["turns"], s["seconds"]), (400, 4, 61))

    def test_banner_lines_are_skipped(self):
        s = self.summarize("START COMPLETE — READY", tool_use("Edit"), RESULT_OK)
        self.assertEqual(s["tools"], {"Edit": 1})

    def test_a_permission_denial_is_counted_not_parsed_as_a_message(self):
        denied = event("system", subtype="permission_denied", message="This Bash command requires approval")
        s = self.summarize(tool_use("Bash"), denied, RESULT_OK)
        self.assertEqual((s["tools"], s["denied"]), ({"Bash": 1}, 1))

    def test_a_run_that_hit_its_cap_did_not_deliver(self):
        capped = event("result", subtype="error_max_budget_usd", is_error=True, num_turns=9, usage={})
        self.assertFalse(self.summarize(tool_use("Read"), capped)["delivered"])

    def test_the_start_banner_rows_are_recorded(self):
        banner = event("system", subtype="hook_response", hook_event="SessionStart", output=json.dumps(
            {"systemMessage": "START COMPLETE — DEGRADED\n  library           ready       picks\n"
                              "  vercel-find       MISSING     search\n  update-tools      never run   x"}))
        s = self.summarize(banner, RESULT_OK)
        self.assertEqual(s["start"], "START COMPLETE — DEGRADED")
        self.assertEqual(s["capabilities"], {"library": "ready", "vercel-find": "MISSING",
                                             "update-tools": "never run"})

    def test_the_degraded_reason_is_recorded(self):
        banner = event("system", subtype="hook_response", hook_event="SessionStart", output=json.dumps(
            {"systemMessage": "START ready\n  library           ready       picks\n\nRouter: CLAUDE.md\n"
                              "Degraded: the last daily dev-check failed: dev-check — x.log\nSee README"}))
        s = self.summarize(banner, RESULT_OK)
        self.assertEqual(s["degraded"], ["the last daily dev-check failed: dev-check — x.log"])
        self.assertEqual(self.summarize(RESULT_OK)["degraded"], [])

    def test_prompt_hook_output_is_counted(self):
        hook = event("system", subtype="hook_response", hook_event="UserPromptSubmit", output="picks: x")
        s = self.summarize(hook, hook, RESULT_OK)
        self.assertEqual((s["prompt_hooks"], s["prompt_hook_chars"]), (2, 16))

    def test_a_run_with_no_result_event_did_not_deliver(self):
        s = self.summarize(tool_use("Read"))
        self.assertFalse(s["delivered"])
        self.assertEqual(s["tokens"], 0)


class RunTests(unittest.TestCase):
    """probe.run against a scratch repository, with the claude call replaced."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.repo = Path(self.folder.name) / "repo"
        self.repo.mkdir()
        (self.repo / "note.md").write_text("x\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base"]):
            probe.git(*args, cwd=self.repo)
        self.out = Path(self.folder.name) / "runs"
        task = Path(self.folder.name) / "task.md"
        task.write_text("write a note\n", encoding="utf-8")
        self.args = probe.argparse.Namespace(task=str(task), label="base", out=str(self.out), patch=None,
                                             ref="HEAD", tools="Read", max_usd=1.0, timeout=5,
                                             model=None, keep=False)
        patches = [mock.patch.object(probe, "ROOT", self.repo),
                   mock.patch.object(probe.shutil, "which", return_value="claude")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_with(self, claude):
        real = subprocess.run

        def fake(cmd, **kw):
            return claude(cmd, **kw) if cmd[0] == "claude" else real(cmd, **kw)
        with mock.patch.object(probe.subprocess, "run", side_effect=fake), \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            code = probe.run(self.args)
        return code, json.loads((self.out / "base.summary.json").read_text(encoding="utf-8"))

    def test_a_timed_out_run_keeps_its_diff_and_summary(self):
        def claude(cmd, cwd, **kw):
            (Path(cwd) / "half.md").write_text("half\n", encoding="utf-8")
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        code, s = self.run_with(claude)
        self.assertEqual((code, s["exit"], s["delivered"]), (1, "timeout", False))
        self.assertIn("half.md", (self.out / "base.diff").read_text(encoding="utf-8"))

    def test_a_nonzero_exit_is_not_delivered(self):
        def claude(cmd, stdout, **kw):
            stdout.write(RESULT_OK + "\n")
            return subprocess.CompletedProcess(cmd, 1, stderr="crash")
        code, s = self.run_with(claude)
        self.assertEqual((code, s["delivered"]), (1, False))

    def test_the_ref_is_recorded_as_the_commit_it_resolved_to(self):
        def claude(cmd, stdout, **kw):
            stdout.write(RESULT_OK + "\n")
            return subprocess.CompletedProcess(cmd, 0, stderr="")
        code, s = self.run_with(claude)
        self.assertEqual(code, 0)
        self.assertEqual(s["ref"], probe.git("rev-parse", "HEAD", cwd=self.repo).strip())

    def test_the_run_asks_for_every_hook_event(self):
        seen = {}

        def claude(cmd, stdout, **kw):
            seen["cmd"] = cmd
            stdout.write(RESULT_OK + "\n")
            return subprocess.CompletedProcess(cmd, 0, stderr="")
        self.run_with(claude)
        self.assertIn("--include-hook-events", seen["cmd"])  # else prompt hooks are not streamed

    def add_clones(self):
        """Harness/repos.txt naming one present clone, a runtime and a tracked skill link into the clone."""
        library = self.repo / "Harness"
        library.mkdir()
        (library / "repos.txt").write_text("# comment\nHarness/kept\turl\tpin\nHarness/absent\turl\tpin\n",
                                           encoding="utf-8")
        (library / "kept").mkdir()
        (library / "kept" / "SKILL.md").write_text("clone\n", encoding="utf-8")
        (library / ".runtime").mkdir()
        (self.repo / ".gitignore").write_text("/Harness/kept/\n/Harness/.runtime/\n", encoding="utf-8")
        probe.git("config", "core.symlinks", "true", cwd=self.repo)
        probe.git("add", "-A", cwd=self.repo)
        # A tracked skill link into a clone, as .claude/skills/grilling is in dev.
        blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=self.repo, input=b"../Harness/kept",
                              capture_output=True, check=True).stdout.decode().strip()
        probe.git("update-index", "--add", "--cacheinfo", "120000,{},skills/kept".format(blob), cwd=self.repo)
        probe.git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "repos", cwd=self.repo)
        return library

    def test_symlinked_clones_stay_out_of_the_diff(self):
        # Off Windows the links are symlinks, which an ignore pattern ending in "/" does not match.
        self.add_clones()

        def claude(cmd, stdout, **kw):
            stdout.write(RESULT_OK + "\n")
            return subprocess.CompletedProcess(cmd, 0, stderr="")
        if os.name == "nt":  # make symlinks here too, not junctions
            import _winapi
            with mock.patch.object(_winapi, "CreateJunction",
                                   lambda src, dst: os.symlink(src, dst, target_is_directory=True)):
                self.run_with(claude)
        else:
            self.run_with(claude)
        self.assertNotIn("120000", (self.out / "base.diff").read_text(encoding="utf-8"))

    def test_present_clones_are_linked_into_the_probe_and_unlinked_after(self):
        library = self.add_clones()
        seen = {}

        def claude(cmd, cwd, stdout, **kw):
            seen["clone"] = (Path(cwd) / "Harness" / "kept" / "SKILL.md").is_file()
            link = Path(cwd) / "skills" / "kept"
            # The preflight's test: on Windows a link git made before its target existed is a file link.
            seen["skill"] = (link / "SKILL.md").is_file() and (
                os.name != "nt" or bool(os.lstat(link).st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY))
            seen["tree"] = Path(cwd)
            stdout.write(RESULT_OK + "\n")
            return subprocess.CompletedProcess(cmd, 0, stderr="")
        code, s = self.run_with(claude)
        self.assertTrue(seen["clone"])
        self.assertTrue(seen["skill"])  # git made the link after its target existed
        self.assertEqual(s["links"], ["Harness/kept", "Harness/.runtime"])
        self.assertNotIn("kept", (self.out / "base.diff").read_text(encoding="utf-8"))
        self.assertFalse(seen["tree"].exists())
        self.assertTrue((library / "kept" / "SKILL.md").is_file())  # the source survives removal

    def test_a_label_with_evidence_already_is_refused(self):
        self.out.mkdir()
        (self.out / "base.jsonl").write_text("", encoding="utf-8")
        with self.assertRaises(SystemExit):
            probe.run(self.args)


if __name__ == "__main__":
    unittest.main()
