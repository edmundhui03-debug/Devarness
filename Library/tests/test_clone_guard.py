"""The vendored clones in Library/repos.txt cannot steer a dev session.

Their CLAUDE.md files are excluded through claudeMdExcludes, and the workshop
clone's skills and commands are denied by name. Claude Code 2.1.274 matches the
excludes with picomatch against absolute paths; every glob here has the one
shape **/<manifest path>/**, which matches any absolute path containing
/<manifest path>/, and that is what matches() below checks.
"""
from pathlib import Path
import json
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = ROOT / ".claude" / "settings.json"
MANIFEST = ROOT / "Library" / "repos.txt"


def settings():
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def clone_paths():
    """Every checkout of somebody else's repository that sits inside dev.

    A vendored clone arrives with its own CLAUDE.md and its own .claude/skills,
    and a session working inside one would load them — which is the thing this
    guard exists to stop. dev carries no mirrors; the old workspace's SAMPLE_FIRMWARE mirrors stayed there.
    """
    return [line.split("\t")[0] for line in MANIFEST.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def glob_for(path):
    return "**/" + path + "/**"


def matches(glob, absolute):
    if not (glob.startswith("**/") and glob.endswith("/**")):
        raise AssertionError("unexpected glob shape: " + glob)
    return "/" + glob[3:-3] + "/" in absolute.replace("\\", "/")


class ClaudeMdExcludes(unittest.TestCase):
    def test_every_clone_in_the_manifest_has_its_exclude(self):
        excludes = settings().get("claudeMdExcludes", [])
        missing = [p for p in clone_paths() if glob_for(p) not in excludes]
        self.assertEqual(missing, [], "clones whose CLAUDE.md files would load")

    def test_no_exclude_outlives_its_clone(self):
        expected = {glob_for(p) for p in clone_paths()}
        stale = [g for g in settings().get("claudeMdExcludes", []) if g not in expected]
        self.assertEqual(stale, [], "excludes with no clone in Library/repos.txt")

    def test_no_tracked_dev_note_is_excluded(self):
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", "*CLAUDE.md", ".claude/rules/*"],
            capture_output=True, check=True, timeout=30,
        ).stdout.decode("utf-8").split("\0")
        notes = [n for n in tracked if n]
        self.assertIn("CLAUDE.md", notes)
        hidden = [
            n for n in notes
            for g in settings().get("claudeMdExcludes", [])
            if matches(g, str(ROOT / n))
        ]
        self.assertEqual(hidden, [], "dev's own notes hidden by an exclude")

    def test_the_globs_name_no_machine(self):
        for glob in settings().get("claudeMdExcludes", []):
            self.assertTrue(glob.startswith("**/"), glob)
            for fragment in ("/Users/", "/home/", ":\\", "C:/"):
                self.assertNotIn(fragment, glob)


if __name__ == "__main__":
    unittest.main()
