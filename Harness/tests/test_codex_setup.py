#!/usr/bin/env python3
"""codex-setup gives Codex the superpowers commit that Claude installed.

Run: python3 Harness/tests/test_codex_setup.py

Codex installs a marketplace's plugin with git, and Claude's plugin cache
became a plain copy on 2026-09-24, so Codex stayed on superpowers 6.3.0 while
Claude ran 6.4.1. codex-setup now adds superpowers' upstream at the commit
Claude's plugin registry records.
"""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
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

    def test_only_the_pocock_skills_the_owner_kept_are_linked(self):
        # Owner decision 2026-10-07: the plugin is off; grill-me, grilling and
        # retro stay, because grill-first and retro-last build on them; and
        # 2026-10-15: writing-for-agents, which retro loads first.
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

    def test_no_skill_is_linked_into_research(self):
        self.assertFalse(hasattr(self.mod, "scholar_links"))
        self.assertNotIn("Research/", TOOL.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
