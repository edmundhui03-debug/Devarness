"""dev's house checkers leave the owner's separate projects and vendored clones alone.

Harness/separate-projects.txt lists the separate projects once, and Harness/repos.txt
lists the vendored clones. md-format and i18n each walk nested repositories to
find satellite projects; these tests build a fake workspace with a satellite, a
listed separate project at each depth and a vendored clone, each holding a file
that breaks the house format, and require only the satellite's to be reported.
dev's own list holds the projects imported into Projects/ that keep their own repository, so
the fixture writes its own.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LIST = ROOT / "Harness" / "separate-projects.txt"
BASH = shutil.which("bash")


def entries(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, timeout=60)


def nested_repo(root, relative, filename, text):
    repo = root / relative
    repo.mkdir(parents=True, exist_ok=True)
    git("init", "-q", cwd=repo)
    (repo / filename).write_text(text, encoding="utf-8")
    git("add", filename, cwd=repo)
    return repo


def fake_root(root):
    """A dev root that the tools recognise, with its own copies of both lists."""
    (root / ".claude").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("# fake\n", encoding="utf-8")
    (root / "Harness" / "bin").mkdir(parents=True)
    (root / "Harness" / "separate-projects.txt").write_text(
        "# fixture\nUpstreamMirror\nProjects/Imported\n", encoding="utf-8")
    (root / "Harness" / "repos.txt").write_text(
        "Harness/vendor\thttps://example.invalid/vendor.git\t" + "0" * 40 + "\n", encoding="utf-8")
    git("init", "-q", cwd=root)
    git("add", "CLAUDE.md", cwd=root)


class TheList(unittest.TestCase):
    def test_every_listed_project_is_also_ignored_by_git(self):
        for name in entries(LIST):
            with self.subTest(name):
                ignored = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", name + "/"],
                                         timeout=30).returncode
                self.assertEqual(ignored, 0, name + " is listed but not in .gitignore")

    def test_none_of_the_old_projects_is_listed_in_dev(self):
        # DATASET_AI, the SAMPLE_FIRMWARE mirrors and Example App stayed in the old workspace (design spec, 2026-10-08).
        names = entries(LIST)
        for kept_behind in ("Projects/DATASET_AI", "SAMPLE_FIRMWARE_upstream",
                           "PCB Tools/AGENTS/Example_App", "PCB Tools/AGENTS/Example_App_MCP"):
            self.assertNotIn(kept_behind, names)


class MdFormat(unittest.TestCase):
    BAD = "no title, no header block, and a line that runs on and on well past the eighty column limit\n"

    def test_only_the_satellite_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_root(root)
            shutil.copy2(ROOT / "Harness" / "bin" / "md-format", root / "Harness" / "bin" / "md-format")
            nested_repo(root, "Satellite", "satellite.md", self.BAD)
            nested_repo(root, "UpstreamMirror", "mirror.md", self.BAD)
            nested_repo(root, "Projects/Imported", "imported.md", self.BAD)
            nested_repo(root, "Harness/vendor", "vendor.md", self.BAD)
            done = subprocess.run(["python3", str(root / "Harness" / "bin" / "md-format"), "check"],
                                  cwd=str(root), capture_output=True, text=True, timeout=120)
            output = done.stdout + done.stderr
            self.assertIn("satellite.md", output)
            for name in ("mirror.md", "imported.md", "vendor.md"):
                self.assertNotIn(name, output)


@unittest.skipUnless(BASH, "bash runs i18n")
class KbI18n(unittest.TestCase):
    PAGE = "<!doctype html><html><body><p>English only</p></body></html>\n"

    def test_only_the_satellite_is_checked(self):
        probe = subprocess.run([BASH, str(ROOT / "Harness" / "bin" / "i18n"), "--help"],
                               capture_output=True, text=True, timeout=60)
        if probe.returncode and "needs markitdown's python" in probe.stderr:
            self.skipTest(probe.stderr.strip())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_root(root)
            nested_repo(root, "Satellite", "satellite.html", self.PAGE)
            nested_repo(root, "UpstreamMirror", "mirror.html", self.PAGE)
            nested_repo(root, "Projects/Imported", "imported.html", self.PAGE)
            nested_repo(root, "Harness/vendor", "vendor.html", self.PAGE)
            done = subprocess.run([BASH, str(ROOT / "Harness" / "bin" / "i18n"), "check"],
                                  cwd=str(root), capture_output=True, text=True, timeout=120)
            output = done.stdout + done.stderr
            self.assertIn("satellite.html: no toggle", output)
            for name in ("mirror.html", "imported.html", "vendor.html"):
                self.assertNotIn(name, output)


if __name__ == "__main__":
    unittest.main()
