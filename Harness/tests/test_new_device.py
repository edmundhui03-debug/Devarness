#!/usr/bin/env python3
"""The legacy CLI checks the portable core without installing optional tools."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2]
TOOL = SOURCE / "Harness/bin/new-device"
REQUIRED = ("CLAUDE.md", "AGENTS.md", "LICENSE", "tools/release_check.py",
            ".claude/hooks/guard_git_amend.py")


class PortableDeviceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="portable-device-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "checkout with spaces"
        self.home = self.base / "empty home"
        self.home.mkdir()
        self.populate(self.root)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        PYTHONIOENCODING="utf-8")
        subprocess.run(["git", "init", "-q", str(self.root)], env=self.env,
                       capture_output=True, check=True, timeout=15)

    def populate(self, root):
        for relative in REQUIRED:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("portable fixture\n", encoding="utf-8")
        (root / "Harness").mkdir(exist_ok=True)
        (root / "Harness/repos.txt").write_text(
            "Harness/example\thttps://github.com/example/tool.git\t" + "a" * 40 + "\n",
            encoding="utf-8")

    def run_check(self, *args, root=None, env=None, command=None):
        return subprocess.run((command or [sys.executable, str(TOOL)]) +
                              ["check", "--root", str(root or self.root), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              env=env or self.env, timeout=20,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def report(self, *args, root=None, env=None):
        done = self.run_check("--json", *args, root=root, env=env)
        self.assertNotIn("Traceback", done.stderr)
        return done.returncode, json.loads(done.stdout)

    def test_core_ready_without_optional_sources(self):
        code, data = self.report()
        self.assertEqual(code, 0, data)
        self.assertEqual(data["schema"], 1)
        self.assertTrue(data["core_ready"])
        self.assertEqual(data["missing"], [])
        self.assertEqual(data["optional_sources_present"], 0)
        self.assertEqual(data["optional_sources_total"], 1)
        self.assertNotIn("layers", data)

    def test_text_keeps_the_dev_check_verdict_and_limits_its_scope(self):
        done = self.run_check()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("NEW DEVICE READY", done.stdout)
        self.assertIn("optional", done.stdout.lower())
        self.assertIn("runtime", done.stdout.lower())

    def test_missing_core_file_fails(self):
        (self.root / "AGENTS.md").unlink()
        code, data = self.report()
        self.assertEqual(code, 1)
        self.assertFalse(data["core_ready"])
        self.assertIn("AGENTS.md", data["missing"])

    def test_invalid_or_missing_manifest_fails_without_a_traceback(self):
        manifest = self.root / "Harness/repos.txt"
        for contents in ("../../escape\thttps://github.com/example/tool\t" + "a" * 40,
                         "Harness/example\thttps://example.invalid/tool\t" + "a" * 40,
                         None):
            with self.subTest(contents=contents):
                if contents is None:
                    manifest.unlink()
                else:
                    manifest.write_text(contents + "\n", encoding="utf-8")
                code, data = self.report()
                self.assertEqual(code, 1)
                self.assertFalse(data["core_ready"])
                self.assertTrue(data["missing"])

    def test_selected_folder_must_be_its_own_git_checkout(self):
        for root in (self.root / "nested", self.base / "unversioned"):
            with self.subTest(root=root.name):
                self.populate(root)
                code, data = self.report(root=root)
                self.assertEqual(code, 1)
                self.assertFalse(data["core_ready"])
                self.assertIn("Git checkout", " ".join(data["missing"]))

    def test_root_selects_data_and_never_executed_code(self):
        (self.root / "tools/bootstrap.py").write_text(
            "raise RuntimeError('untrusted target code ran')\n", encoding="utf-8")
        self.assertEqual(self.report()[0], 0)

    def test_git_redirection_cannot_replace_the_selected_checkout(self):
        env = dict(self.env, GIT_DIR=str(self.base / "missing.git"),
                   GIT_WORK_TREE=str(self.base / "wrong worktree"))
        self.assertEqual(self.report(env=env)[0], 0)

    def test_compatibility_options_do_not_read_or_change_home_or_checkout(self):
        profile = self.home / ".config/devarness/personal-repos.txt"
        profile.parent.mkdir(parents=True)
        profile.write_text("Private configuration is not an installation requirement.\n", encoding="utf-8")
        def snapshot():
            return {str(p.relative_to(self.base)): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                                   p.stat().st_mtime_ns)
                    for p in self.base.rglob("*") if p.is_file()}
        before = snapshot()
        self.assertEqual(self.report("--home", str(self.home), "--no-system")[0], 0)
        self.assertEqual(before, snapshot())

    def test_python_network_use_is_forbidden_during_readiness(self):
        hook = ("import runpy, socket, sys\n"
                "def forbidden(*args, **kwargs):\n"
                "    raise AssertionError('readiness attempted network access')\n"
                "socket.socket = forbidden\n"
                "sys.argv = sys.argv[1:]\n"
                "runpy.run_path(sys.argv[0], run_name='__main__')\n")
        done = self.run_check(command=[sys.executable, "-c", hook, str(TOOL)])
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_usage_errors_exit_two(self):
        self.assertEqual(self.run_check(root=self.base / "absent").returncode, 2)
        self.assertEqual(self.run_check("--unknown").returncode, 2)


if __name__ == "__main__":
    unittest.main()
