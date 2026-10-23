#!/usr/bin/env python3
"""The reverse runtime installer and launchers: verify before unpacking, fail closed, pass args through.

Run: python3 Harness/tests/test_reverse.py

These cover the parts that need no downloaded tool: a tampered archive is refused before anything is
unpacked; --check fails on an empty runtime; rea with no runtime exits 3 and says nothing on stdout;
rea passes its arguments through and returns the child's exit code; and no tracked file in this set
carries an absolute machine path. A fake Node (this interpreter) and a fake rea.mjs stand in for the
real runtime, so the suite runs offline in a few seconds.
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
import zipfile

LIBRARY = Path(__file__).resolve().parents[1]
SETUP = LIBRARY / "setup-reverse.py"
DEVARNESS_REA = LIBRARY / "bin" / "rea"
REA_LOCK = LIBRARY / "setup" / "rea" / "package-lock.json"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


setup = load("setup_reverse", SETUP)


def make_fake_zip(path, payload):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("dummy.txt", payload)


class VerifyBeforeUnpack(unittest.TestCase):
    def test_a_tampered_archive_is_refused_before_unpacking(self):
        real = setup.load_manifest()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "dl"
            src.mkdir()
            rt = Path(d) / "rt"
            tools = {}
            for tool in setup.ARCHIVE_TOOLS:
                fname = real[tool]["file"]
                archive = src / fname
                make_fake_zip(archive, b"fake-" + tool.encode())
                sha = setup.sha256_of(archive)
                if tool == "node":            # tamper the expected hash of one archive
                    sha = "0" * 64
                tools[tool] = {"file": fname, "url": "x", "size": archive.stat().st_size, "sha256": sha}
            with self.assertRaises(SystemExit):
                setup.install(str(src), rt, tools)
            # Refused before any unpack: no tool folder, and the runtime root was never created.
            for tool in setup.ARCHIVE_TOOLS:
                self.assertFalse((rt / tool).exists(), "%s was unpacked despite the tamper" % tool)


class CheckFailsClosed(unittest.TestCase):
    def test_check_exits_1_on_an_empty_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            lines, code = setup.check(Path(d))
            self.assertEqual(code, 1)
            self.assertTrue(any("MISSING" in line for line in lines))
        # and through the CLI
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, str(SETUP), "--check", "--runtime-root", d],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)


class DoctorNamesWhatIsNotReady(unittest.TestCase):
    """--check --doctor: the reverse-ready gate. The real run (about 30 s) is in the build report."""

    def run_setup(self, runtime, *extra, env=None):
        return subprocess.run([sys.executable, str(SETUP), "--check", "--doctor", "--runtime-root", str(runtime),
                               *extra], capture_output=True, text=True, encoding="utf-8", timeout=300,
                              env=dict(os.environ, **(env or {})))

    def test_a_missing_runtime_exits_1_with_the_install_command_and_runs_no_doctor(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_setup(Path(d))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("python Harness/setup-reverse.py --from", r.stdout)
            self.assertNotIn("reverse doctor", r.stdout)

    @unittest.skipUnless(os.name == "nt", "the runtime's entry points are Windows builds")
    def test_an_unhealthy_doctor_and_a_tool_that_will_not_start_are_named(self):
        with tempfile.TemporaryDirectory() as d:
            rt = Path(d) / "rt"
            for rel in ("jdk/bin/java.exe", "node/node.exe", "ghidra/support/analyzeHeadless.bat",
                        "apktool/apktool.jar"):
                (rt / rel).parent.mkdir(parents=True, exist_ok=True)
                (rt / rel).write_bytes(b"")
            (rt / "jadx" / "bin").mkdir(parents=True)
            (rt / "jadx" / "bin" / "jadx.bat").write_text("@echo 1.5.6\r\n", encoding="ascii")
            scripts = rt / "rea" / "node_modules" / "rea-agents" / "scripts"
            scripts.mkdir(parents=True)
            # The stand-in REA answers the doctor with one failed scope check.
            (scripts / "rea.mjs").write_text(
                "import json, sys\n"
                "print(json.dumps({'healthy': False, 'scope_checks': [{'name': 'node', 'ok': True},"
                " {'name': 'ghidra-headless', 'ok': False}]}))\n"
                "sys.exit(1)\n", encoding="ascii")
            r = self.run_setup(rt, env={"DEVARNESS_REVERSE_NODE": sys.executable})
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("reverse doctor", r.stdout)
            last = r.stdout.strip().splitlines()[-1]
            self.assertTrue(last.startswith("reverse tools: NOT READY"), r.stdout)
            self.assertIn("ghidra-headless", last)
            self.assertIn("apktool", last)
            self.assertNotIn("jadx", last)           # its stand-in answered with a version


class ReaNoRuntime(unittest.TestCase):
    def test_rea_with_no_runtime_exits_3_and_is_silent_on_stdout(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, DEVARNESS_REVERSE_RUNTIME=str(Path(d) / "empty"))
            env.pop("DEVARNESS_REVERSE_NODE", None)
            r = subprocess.run([sys.executable, str(DEVARNESS_REA)], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 3)
            self.assertEqual(r.stdout, "")
            self.assertIn("setup-reverse", r.stderr)


class ReaPassesArgsThrough(unittest.TestCase):
    def test_rea_passes_args_through_and_returns_the_child_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            rt = Path(d) / "rt"
            scripts = rt / "rea" / "node_modules" / "rea-agents" / "scripts"
            scripts.mkdir(parents=True)
            out = Path(d) / "args.txt"
            # A fake rea.mjs: this interpreter runs it as the "node" child. It records the argv it was
            # handed and exits with a distinctive code, so the test can read both back.
            (scripts / "rea.mjs").write_text(
                "import os, sys, pathlib\n"
                "pathlib.Path(os.environ['DEVARNESS_FAKE_ARGS_OUT']).write_text("
                "chr(0).join(sys.argv[1:]), encoding='utf-8')\n"
                "sys.exit(7)\n", encoding="ascii")
            env = dict(os.environ,
                       DEVARNESS_REVERSE_RUNTIME=str(rt),
                       DEVARNESS_REVERSE_NODE=sys.executable,
                       DEVARNESS_FAKE_ARGS_OUT=str(out))
            r = subprocess.run([sys.executable, str(DEVARNESS_REA), "mcp", "--flag", "value"],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 7, r.stderr)
            self.assertEqual(r.stdout, "")
            self.assertEqual(out.read_text(encoding="utf-8").split(chr(0)), ["mcp", "--flag", "value"])


class NoMachinePaths(unittest.TestCase):
    def test_no_tracked_file_in_this_set_carries_an_absolute_machine_path(self):
        files = [
            LIBRARY / "setup-reverse.py",
            LIBRARY / "setup" / "reverse-downloads.json",
            LIBRARY / "setup" / "rea" / "package.json",
            LIBRARY / "setup" / "rea" / "package-lock.json",
            LIBRARY / "bin" / "rea",
            LIBRARY / "bin" / "reverse",
            Path(__file__).resolve(),
        ]

        def frag(*xs):   # assemble each needle so this test file never contains one verbatim
            return "".join(xs)
        needles = [
            frag("C:", "\\", "U", "sers", "\\"),
            frag("C:", "/", "U", "sers", "/"),
            frag("/", "U", "sers", "/"),
            frag("/", "ho", "me", "/"),
            frag("/", "App", "lications", "/"),
            frag("/", "pri", "vate", "/", "tmp", "/"),
        ]
        home = os.path.expanduser("~")
        if home and len(home) > 3:
            needles += [home, home.replace("\\", "/")]
        for f in files:
            text = f.read_text(encoding="utf-8", errors="replace")
            for needle in needles:
                self.assertNotIn(needle, text, "%s contains the machine path %r" % (f.name, needle))


class LockMatchesPin(unittest.TestCase):
    def test_the_tracked_lock_pins_rea_agents_to_the_expected_integrity(self):
        lock = json.loads(REA_LOCK.read_text(encoding="utf-8"))
        self.assertEqual(lock["packages"]["node_modules/rea-agents"]["integrity"], setup.REA_INTEGRITY)
        self.assertEqual(lock["packages"]["node_modules/rea-agents"]["version"], "4.1.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
