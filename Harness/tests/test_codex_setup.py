#!/usr/bin/env python3
"""codex-setup gives Codex the superpowers revision registered by Claude.

Run: python3 Harness/tests/test_codex_setup.py

Codex receives a Git marketplace pinned to the registered upstream revision
instead of depending on the layout of Claude's plugin cache.
"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "Harness" / "codex-setup.py"


def load():
    loader = importlib.machinery.SourceFileLoader("codex_setup", str(TOOL))
    spec = importlib.util.spec_from_loader("codex_setup", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class CliTests(unittest.TestCase):
    def test_help_and_unknown_options_exit_before_setup(self):
        with tempfile.TemporaryDirectory(prefix="codex-setup-cli-") as folder:
            root = Path(folder)
            registry = root / ".claude/plugins/installed_plugins.json"
            registry.parent.mkdir(parents=True)
            registry.write_text('{"plugins": {}}', encoding="utf-8")
            env = dict(os.environ, HOME=folder, USERPROFILE=folder, PATH="")
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            for option, expected in (("--help", 0), ("--unknown-option", 2)):
                with self.subTest(option=option):
                    done = subprocess.run([sys.executable, str(TOOL), option], cwd=folder,
                                          env=env, capture_output=True, text=True, timeout=10)
                    self.assertEqual(done.returncode, expected, done.stdout + done.stderr)
                    self.assertIn("usage:", done.stdout + done.stderr)
                    self.assertNotIn("plugin registry", done.stdout + done.stderr)
                    self.assertEqual(
                        {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()},
                        before)


class ClaudeCommitTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.temporary = tempfile.TemporaryDirectory(prefix="codex-start-setup-")
        self.mod.REGISTRY = Path(self.temporary.name) / "installed_plugins.json"

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, plugins):
        self.mod.REGISTRY.write_text(json.dumps({"version": 2, "plugins": plugins}),
                                     encoding="utf-8")

    def test_the_commit_is_the_one_claude_installed(self):
        self.write({"superpowers@claude-plugins-official": [
            {"scope": "user", "version": "6.4.1", "gitCommitSha": "5bf4e78"}]})
        self.assertEqual(self.mod.claude_commit("superpowers@claude-plugins-official"),
                         "5bf4e78")

    def test_a_plugin_claude_has_not_installed_stops_the_setup(self):
        self.write({})
        with self.assertRaises(SystemExit):
            self.mod.claude_commit("superpowers@claude-plugins-official")


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()

    def test_only_the_shared_pocock_skills_are_linked(self):
        # These shared skills support grill-first, retro-last and retro's
        # writing-for-agents guide.
        self.assertEqual(self.mod.POCOCK, ("productivity/grill-me", "productivity/grilling",
                                           "engineering/retro", "productivity/writing-for-agents"))
        if not (ROOT / "Harness/skills/skills").is_dir():
            self.skipTest("the pinned Pocock clone is not on this device")
        for skill in self.mod.POCOCK:
            self.assertTrue((ROOT / "Harness/skills/skills" / skill / "SKILL.md").is_file(), skill)

    def test_setup_restores_the_shared_intake_skill(self):
        success = Mock(returncode=0)
        with patch.object(self.mod, "claude_commit", return_value="fixture-pin"), \
                patch.object(self.mod.subprocess, "run", return_value=success) as run, \
                patch.object(self.mod, "link") as link:
            self.mod.main()
        link.assert_any_call(ROOT / ".claude/skills/library-intake",
                             ROOT / ".agents/skills/library-intake")
        link.assert_any_call(ROOT / ".claude/skills/library",
                             ROOT / ".agents/skills/library")
        self.assertFalse(any('ecc@ecc' in call.args[0] for call in run.call_args_list))

    def test_marketplace_add_failure_preserves_the_existing_registration(self):
        failure = Mock(returncode=1, stdout="", stderr="temporary connection failure")
        success = Mock(returncode=0, stdout="", stderr="")
        exit_message = None
        with patch.object(self.mod, "claude_commit", return_value="fixture-pin"), \
                patch.object(self.mod.subprocess, "run", side_effect=[failure, success, success, success]) as run, \
                patch.object(self.mod, "link"):
            try:
                self.mod.main()
            except SystemExit as error:
                exit_message = str(error)
        self.assertEqual([call.args[0][1:4] for call in run.call_args_list],
                         [["plugin", "marketplace", "add"]])
        self.assertIsNotNone(exit_message)
        self.assertIn("temporary connection failure", exit_message)

    def test_no_skill_is_linked_into_research(self):
        self.assertFalse(hasattr(self.mod, "scholar_links"))
        self.assertNotIn("Research/", TOOL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
