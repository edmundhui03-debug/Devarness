#!/usr/bin/env python3
"""codex-hook-trust: a dev Codex hook that Codex does not trust never runs.

Run: python3 Harness/tests/test_codex_hook_trust.py

Aster's turn-end phone alert sat untrusted from 2026-10-03 to 2026-10-07,
and her session-start check ran on a stale trust: editing .codex/hooks.json
drops Codex's trust, and nothing checked. These tests drive the checker
against a fake `codex app-server` that answers the documented hooks/list and
config/batchWrite methods, so no real Codex runs and nothing is trusted here.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "Harness" / "codex-hook-trust.py"

# A fake app-server: newline-delimited JSON on stdin and stdout, answering
# from FAKE_STATE (a JSON file) and appending batchWrite calls to FAKE_LOG.
FAKE = r'''
import json, os, sys
state = json.load(open(os.environ["FAKE_STATE"], encoding="utf-8"))
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    method, rid = msg["method"], msg["id"]
    if method in state.get("hang", []):
        continue
    if method in state.get("errors", []):
        reply = {"id": rid, "error": {"message": "fake failure"}}
    elif method == "initialize":
        reply = {"id": rid, "result": {}}
    elif method == "hooks/list":
        reply = {"id": rid, "result": {"data": [{"cwd": msg["params"]["cwds"][0], "errors": [], "warnings": [],
                                                  "hooks": state["hooks"]}]}}
    elif method == "config/batchWrite":
        with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
            log.write(json.dumps(msg["params"]) + "\n")
        # Like Codex, a hook is trusted only by the hash it actually has.
        written = msg["params"]["edits"][0]["value"]
        for hook in state["hooks"]:
            if written.get(hook["key"], {}).get("trusted_hash") == hook["currentHash"]:
                hook["trustStatus"] = "trusted"
        reply = {"id": rid, "result": {}}
    else:
        reply = {"id": rid, "error": {"message": "unknown method " + method}}
    sys.stdout.write(json.dumps(reply) + "\n")
    sys.stdout.flush()
'''


class HookTrustTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hook-trust-")
        self.addCleanup(temporary.cleanup)
        # resolve(): TEMP may hold an 8.3 short name, while the tool compares
        # the long path it resolved.
        self.root = Path(temporary.name).resolve()
        self.workspace = self.root / "dev"
        (self.workspace / ".codex").mkdir(parents=True)
        (self.workspace / ".codex" / "hooks.json").write_text(json.dumps({"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "start"}]}],
            "Stop": [{"hooks": [{"type": "command", "command": "notify"}]}]}}), encoding="utf-8")
        self.codex_home = self.root / "codex-home"
        self.codex_home.mkdir()
        (self.codex_home / "config.toml").write_text("model = \"x\"\n", encoding="utf-8")
        self.fake = self.root / "fake_codex.py"
        self.fake.write_text(FAKE, encoding="utf-8")
        self.state = self.root / "state.json"
        self.log = self.root / "batch.log"

    def hook(self, event, key, status, enabled=True):
        source = str(self.workspace / ".codex" / "hooks.json")
        return {"eventName": event, "key": source + ":" + key, "trustStatus": status, "enabled": enabled,
                "currentHash": "sha256:" + key, "sourcePath": source, "source": "project",
                "command": "python3 run-" + key, "matcher": None}

    def run_tool(self, hooks, *args, errors=(), hang=(), codex=None):
        self.state.write_text(json.dumps({"hooks": hooks, "errors": list(errors), "hang": list(hang)}),
                              encoding="utf-8")
        env = dict(os.environ, DEVARNESS_CODEX_BIN=str(codex or self.fake), FAKE_STATE=str(self.state),
                   FAKE_LOG=str(self.log), CODEX_HOME=str(self.codex_home), DEVARNESS_HOOK_TRUST_DEADLINE="3")
        done = subprocess.run([sys.executable, str(TOOL), "--root", str(self.workspace), *args], env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
        return done.returncode, done.stdout + done.stderr

    def test_all_dev_hooks_trusted_passes(self):
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "trusted"),
                                 self.hook("stop", "stop:0:0", "trusted")], "--check")
        self.assertEqual(rc, 0, out)
        self.assertIn("2 of 2 dev hooks trusted", out)

    def test_a_modified_hook_fails_and_is_named(self):
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "modified"),
                                 self.hook("stop", "stop:0:0", "trusted")], "--check")
        self.assertEqual(rc, 1, out)
        self.assertIn("session_start:0:0", out)
        self.assertIn("modified", out)

    def test_an_untrusted_hook_fails(self):
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "trusted"),
                                 self.hook("stop", "stop:0:0", "untrusted")], "--check")
        self.assertEqual(rc, 1, out)
        self.assertIn("stop:0:0", out)

    def test_a_hook_codex_does_not_list_fails(self):
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "trusted")], "--check")
        self.assertEqual(rc, 1, out)
        self.assertIn("1 of 2", out)

    def test_an_app_server_error_is_an_error_not_a_pass(self):
        rc, out = self.run_tool([], "--check", errors=("hooks/list",))
        self.assertEqual(rc, 2, out)

    def test_a_device_without_codex_is_not_applicable(self):
        rc, out = self.run_tool([], "--check", codex=self.root / "no-codex-here.exe")
        self.assertEqual(rc, 3, out)

    def test_trust_writes_the_exact_hash_for_dev_hooks_only_and_backs_up(self):
        other = {"eventName": "stop", "key": "elsewhere:stop:0:0", "trustStatus": "untrusted", "enabled": True,
                 "currentHash": "sha256:other", "sourcePath": str(self.root / "elsewhere.json"), "source": "user"}
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "modified"),
                                 self.hook("stop", "stop:0:0", "trusted"), other], "--trust", "--yes")
        self.assertEqual(rc, 0, out)
        written = json.loads(self.log.read_text(encoding="utf-8").splitlines()[0])
        key = str(self.workspace / ".codex" / "hooks.json") + ":session_start:0:0"
        self.assertEqual(written["edits"][0]["value"], {key: {"trusted_hash": "sha256:session_start:0:0"}})
        self.assertEqual(written["edits"][0]["keyPath"], "hooks.state")
        self.assertEqual(written["edits"][0]["mergeStrategy"], "upsert")
        self.assertTrue(list(self.codex_home.glob("config.toml.bak-hook-trust-*")))

    def test_trust_without_yes_shows_the_commands_and_writes_nothing(self):
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "modified"),
                                 self.hook("stop", "stop:0:0", "trusted")], "--trust")
        self.assertEqual(rc, 1, out)
        self.assertIn("python3 run-session_start:0:0", out)
        self.assertFalse(self.log.exists())

    def test_trust_with_nothing_to_do_writes_nothing(self):
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "trusted"),
                                 self.hook("stop", "stop:0:0", "trusted")], "--trust", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertFalse(self.log.exists())

    def test_a_trusted_but_disabled_hook_fails(self):
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "trusted"),
                                 self.hook("stop", "stop:0:0", "trusted", enabled=False)], "--check")
        self.assertEqual(rc, 1, out)
        self.assertIn("disabled", out)

    def test_an_app_server_that_never_answers_is_an_error_within_the_deadline(self):
        start = time.monotonic()
        rc, out = self.run_tool([], "--check", hang=("hooks/list",))
        self.assertEqual(rc, 2, out)
        self.assertLess(time.monotonic() - start, 30, out)

    def test_a_failed_trust_write_is_an_error(self):
        rc, out = self.run_tool([self.hook("sessionStart", "session_start:0:0", "modified"),
                                 self.hook("stop", "stop:0:0", "trusted")], "--trust", "--yes",
                                errors=("config/batchWrite",))
        self.assertEqual(rc, 2, out)

    def test_a_source_path_in_another_case_still_counts(self):
        hooks = [self.hook("sessionStart", "session_start:0:0", "trusted"), self.hook("stop", "stop:0:0", "trusted")]
        for hook in hooks:
            hook["sourcePath"] = hook["sourcePath"].upper()
        rc, out = self.run_tool(hooks, "--check")
        self.assertEqual(rc, 0, out)

    def trust_project(self, level="trusted"):
        key = str(self.workspace.resolve()).replace("'", "")
        (self.codex_home / "config.toml").write_text(
            "model = \"x\"\n[projects.'%s']\ntrust_level = \"%s\"\n" % (key, level), encoding="utf-8")

    def test_fewer_listed_hooks_points_at_the_project_not_at_trust(self):
        self.trust_project()
        rc, out = self.run_tool([], "--check")
        self.assertEqual(rc, 1, out)
        self.assertIn("Codex lists 0 of 2 dev hooks", out)

    def test_a_folder_codex_was_never_asked_to_trust_is_the_owners_step(self):
        # A new device: Codex runs, but nobody has trusted dev in it yet.
        rc, out = self.run_tool([], "--check")
        self.assertEqual(rc, 3, out)
        self.assertIn("/hooks", out)
        self.assertFalse(self.log.exists())

    def test_a_declined_folder_still_fails(self):
        self.trust_project("untrusted")
        rc, out = self.run_tool([], "--check")
        self.assertEqual(rc, 1, out)

    def test_a_codex_home_that_does_not_exist_is_not_applicable(self):
        (self.codex_home / "config.toml").unlink()
        self.codex_home.rmdir()
        rc, out = self.run_tool([], "--check")
        self.assertEqual(rc, 3, out)
        self.assertFalse(self.codex_home.exists())


if __name__ == "__main__":
    unittest.main()
