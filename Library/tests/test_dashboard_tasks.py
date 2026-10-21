"""PRD R4, end to end on a real md-format: a needs-owner section planted in a
test document appears on /api/tasks, and once marked fixed it is answered as
fixed; the app's columns are what take a fixed section off the board."""
import ast
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "Library" / "dashboard" / "server" / "server.mjs"
MD_FORMAT = ROOT / "Library" / "bin" / "md-format"
NODE = shutil.which("node")
GIT = shutil.which("git")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
KEEP = ("PATH", "SYSTEMROOT", "USERPROFILE", "HOME", "TEMP", "TMP")


def small_env():
    """A small environment of its own for each child, never the whole one (LESSONS.md:460)."""
    return {key: os.environ[key] for key in KEEP if key in os.environ}

PLANTED = """# A planted document shows the Tasks page follows the index

> **2026-10-14** · Peter · `draft`
>
> Written by the R4 test and removed with its folder.

## The planted decision waits for the owner

`{state}` · planted by the test
"""


@unittest.skipUnless(NODE and GIT, "node and git are needed")
class PlantedSectionTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="dash-r4-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        # md-format's root is the first parent holding CLAUDE.md and .claude/.
        (self.root / ".claude").mkdir()
        (self.root / "CLAUDE.md").write_text("# A test root\n", encoding="utf-8")
        (self.root / "Library" / "bin").mkdir(parents=True)
        shutil.copy2(MD_FORMAT, self.root / "Library" / "bin" / "md-format")
        self.doc = self.root / "Setup" / "planted.md"
        self.doc.parent.mkdir()
        self.doc.write_text(PLANTED.format(state="needs-owner"), encoding="utf-8")
        for args in (["init", "-q"], ["add", "Setup/planted.md"]):
            subprocess.run([GIT, "-C", str(self.root), *args], check=True,
                           capture_output=True, env=small_env(), creationflags=NO_WINDOW)

    def start(self):
        env = small_env()
        env["DEVARNESS_PYTHON"] = sys.executable
        env["CODEX_CMD"] = json.dumps([str(self.root / "no-codex.exe")])
        proc = subprocess.Popen(
            [NODE, str(SERVER), "--port", "0", "--root", str(self.root),
             "--home", str(self.root), "--questions", str(self.root / "questions.json"),
             "--dist", str(self.root / "dist")],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            env=env, creationflags=NO_WINDOW)
        self.addCleanup(proc.stdout.close)  # cleanups run last first: kill, wait, then close
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.kill)
        for line in proc.stdout:
            found = re.search(r"http://127\.0\.0\.1:(\d+)", line)
            if found:
                return int(found.group(1))
        self.fail("the server did not start")

    def planted(self, port):
        # http.client, never urllib: a system proxy cannot reach this machine's loopback.
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        try:
            conn.request("GET", "/api/tasks")
            res = conn.getresponse()
            self.assertEqual(res.status, 200)
            body = json.load(res)
        finally:
            conn.close()
        self.assertEqual(body["code"], "ok")
        return [(s["status"], s["heading"]) for s in body["sections"] if s["file"] == "Setup/planted.md"]

    def test_planted_section_appears_then_leaves_once_fixed(self):
        port = self.start()
        heading = "The planted decision waits for the owner"
        self.assertEqual(self.planted(port), [("needs-owner", heading)])
        self.doc.write_text(PLANTED.format(state="fixed"), encoding="utf-8")
        time.sleep(2.5)  # past the 2 s for which polls share one reading
        self.assertEqual(self.planted(port), [("fixed", heading)])


class SmallEnvironmentTest(unittest.TestCase):
    def test_every_child_gets_a_small_environment(self):
        # LESSONS.md:460: a child given no env inherits the whole one, and
        # dict(os.environ, ...) or a loop over os.environ.items() copies it.
        found = []
        for name in ("test_dashboard.py", "test_dashboard_bridge.py", "test_dashboard_tasks.py"):
            tree = ast.parse(Path(__file__).with_name(name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if ast.unparse(node).startswith(("dict(os.environ", "os.environ.items(", "os.environ.copy(")):
                    found.append(f"{name}:{node.lineno} copies it")
                elif (isinstance(node.func, ast.Attribute) and node.func.attr in ("run", "Popen")
                      and not any(keyword.arg == "env" for keyword in node.keywords)):
                    found.append(f"{name}:{node.lineno} gives no env")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
