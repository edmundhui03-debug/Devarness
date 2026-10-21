#!/usr/bin/env python3
"""scholar-sync.sh installs the curated claude-scholar subset into a project.

Run: python3 Library/tests/test_scholar_sync.py

The project folder is an argument: dev has no Research/ of its own, and a
script that assumed one installed into the wrong place once a folder was
renamed (M16). The test builds a fake dev with a stand-in clone and runs the
real script on it, with Git for Windows' bash on Windows.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "Library" / "scholar-sync.sh"


def bash():
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    for folder in list(Path(git).resolve().parents)[:3] if git else []:
        if (folder / "bin" / "bash.exe").is_file():
            return str(folder / "bin" / "bash.exe")
    return None


def listed(name):
    """An allowlist as the script holds it, so the fixture cannot drift from it."""
    block = re.search(r"^%s=\(\n(.*?)^\)" % name, SCRIPT.read_text(encoding="utf-8"), re.M | re.S).group(1)
    return [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith("#")]


@unittest.skipUnless(bash(), "Git Bash's bash is needed")
class ScholarSyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="scholar-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        clone = self.root / "Library" / "claude-scholar"
        (clone / ".claude-plugin").mkdir(parents=True)
        (clone / ".claude-plugin" / "plugin.json").write_text("{}\n", encoding="utf-8")
        for skill in listed("SKILLS"):
            (clone / "skills" / skill).mkdir(parents=True)
            (clone / "skills" / skill / "SKILL.md").write_text(
                "---\nname: %s\ndescription: x\n---\n" % skill, encoding="utf-8")
        guide = clone / "skills" / "research-ideation" / "references" / "zotero-integration-guide.md"
        guide.parent.mkdir()
        guide.write_text("pruned by the script\n", encoding="utf-8")
        for folder, names in (("agents", listed("AGENTS")), ("commands", listed("COMMANDS"))):
            (clone / folder).mkdir()
            for name in names:
                (clone / folder / (name + ".md")).write_text("# %s\n" % name, encoding="utf-8")
        shutil.copy2(SCRIPT, self.root / "Library" / "scholar-sync.sh")
        self.project = self.root / "Projects" / "My Papers"
        self.project.mkdir(parents=True)

    def sync(self, *args):
        return subprocess.run([bash(), str(self.root / "Library" / "scholar-sync.sh"), *args],
                              capture_output=True, text=True, timeout=120)

    def test_the_curated_skills_land_in_the_named_project(self):
        done = self.sync(str(self.project))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        skills = self.project / ".claude" / "skills"
        self.assertEqual(sorted(p.parent.name for p in skills.glob("*/SKILL.md")), sorted(listed("SKILLS")))
        self.assertTrue((self.project / ".claude" / "hooks" / "scholar-manifest.txt").is_file())
        self.assertFalse((self.root / "Research").exists())

    def test_a_second_run_leaves_the_install_as_it_was(self):
        self.assertEqual(self.sync(str(self.project)).returncode, 0)
        manifest = (self.project / ".claude" / "hooks" / "scholar-manifest.txt").read_text(encoding="utf-8")
        done = self.sync(str(self.project))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual((self.project / ".claude" / "hooks" / "scholar-manifest.txt").read_text(encoding="utf-8"),
                         manifest)

    def test_no_project_or_a_missing_one_installs_nothing(self):
        for args in ((), (str(self.root / "no such folder"),)):
            with self.subTest(args=args):
                done = self.sync(*args)
                self.assertNotEqual(done.returncode, 0, done.stdout)
                self.assertIn("usage", (done.stdout + done.stderr).lower())
        self.assertEqual(list(self.root.rglob(".claude")), [])


if __name__ == "__main__":
    unittest.main()
