#!/usr/bin/env python3
"""taskboard starts the Codex Taskboard only in its safe shape.

The intake of 2026-10-09 found the server binds every address unless told
otherwise, has no login, and starts Codex on its own; the owner chose a
browser tab only. These tests pin the shape the launcher must always use.
"""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "bin" / "taskboard"


def load():
    loader = importlib.machinery.SourceFileLoader("dev_taskboard", str(TOOL))
    spec = importlib.util.spec_from_loader("dev_taskboard", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class SafeShapeTests(unittest.TestCase):
    def setUp(self):
        self.tb = load()

    def test_the_server_listens_on_this_computer_only(self):
        env = self.tb.server_env({})
        self.assertEqual(env["CODEX_TASKBOARD_HOST"], "127.0.0.1")
        self.assertEqual(env["CODEX_TASKBOARD_PORT"], "47823")

    def test_codex_cannot_be_started_by_the_taskboard(self):
        env = self.tb.server_env({})
        self.assertFalse(Path(env["CODEX_EXECUTABLE"]).exists())

    def test_its_data_lives_outside_the_runtime_copy(self):
        env = self.tb.server_env({"LOCALAPPDATA": r"D:\AppData\Local"})
        data = Path(env["CODEX_TASKBOARD_DATA_DIR"])
        self.assertNotIn(".runtime", data.parts)
        self.assertEqual((data.parent.name, data.name), ("dev", "taskboard"))

    def test_secrets_in_the_environment_are_not_passed_on(self):
        env = self.tb.server_env({"PATH": "p", "ANTHROPIC_API_KEY": "s", "GH_TOKEN": "s",
                                  "SOME_SECRET": "s", "OPENAI_API_KEY": "s"})
        self.assertEqual(env["PATH"], "p")
        for name in ("ANTHROPIC_API_KEY", "GH_TOKEN", "SOME_SECRET", "OPENAI_API_KEY"):
            self.assertNotIn(name, env)

    def test_the_command_runs_the_server_from_the_runtime_copy(self):
        argv, cwd = self.tb.server_command()
        self.assertEqual(Path(argv[-1]).name, "index.mjs")
        self.assertEqual(Path(cwd).name, "dashi-taskboard")
        self.assertIn(".runtime", Path(cwd).parts)


class CommandTests(unittest.TestCase):
    def run_tool(self, *args, env=None):
        return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                              timeout=30, env=env)

    def test_status_says_not_running_on_a_closed_port(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        done = self.run_tool("status", env=dict(os.environ, DEVARNESS_TASKBOARD_PORT=str(port)))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("not running", done.stdout)

    def test_help_shows_both_commands_and_succeeds(self):
        done = self.run_tool("--help")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("taskboard status", done.stdout)
        self.assertEqual(self.run_tool("bogus").returncode, 2)

    def test_start_refuses_without_the_runtime_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = self.run_tool("start", env=dict(os.environ, DEVARNESS_TASKBOARD_RUNTIME=tmp))
        self.assertEqual(done.returncode, 1)
        self.assertIn("not installed", done.stdout + done.stderr)


class HongKongChineseTests(unittest.TestCase):
    """The owner's ruling of 2026-10-10: the board's Chinese is Hong Kong
    Traditional, applied to the runtime copy from a table, never to the clone."""

    def setUp(self):
        self.tb = load()

    def runtime(self, tmp, files):
        for rel, text in files.items():
            path = Path(tmp) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return Path(tmp)

    def test_apply_translates_each_phrase_and_the_date_locale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.runtime(tmp, {
                "web/src/i18n.tsx": 'locale: "zh-CN" | "en";\nconst x = { locale: "zh-CN" };\ntext("处理中", "In progress");\n',
                "server/app.mjs": 'throw new Error("共 ${n} 项");\n',
            })
            missing = self.tb.apply_zh_hk(root, {"处理中": "處理中", "共 ": "共 ", "项": "項"})
            self.assertEqual(missing, [])
            i18n = (root / "web/src/i18n.tsx").read_text(encoding="utf-8")
            self.assertIn('text("處理中", "In progress")', i18n)
            self.assertEqual(i18n.count("zh-HK"), 2)
            self.assertNotIn("zh-CN", i18n)
            self.assertIn("共 ${n} 項", (root / "server/app.mjs").read_text(encoding="utf-8"))

    def test_apply_names_a_phrase_the_table_lacks_and_leaves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.runtime(tmp, {"web/src/App.tsx": 'text("新的简体字", "New words");\n'})
            self.assertEqual(self.tb.apply_zh_hk(root, {}), ["新的简体字"])
            self.assertIn("新的简体字", (root / "web/src/App.tsx").read_text(encoding="utf-8"))

    def test_the_table_is_checked_for_simplified_characters_and_changed_code(self):
        problems = self.tb.table_problems({"我们": "我们", "共 ${n} 项": "共 ${count} 項", "设置": "設定"})
        self.assertEqual(len(problems), 2, problems)  # 们 kept; ${n} renamed

    def test_the_table_holds_no_problem(self):
        self.assertEqual(self.tb.table_problems(self.tb.load_zh_hk()), [])

    def test_every_phrase_of_the_pinned_taskboard_is_translated(self):
        if not (self.tb.SOURCE / "web" / "src").is_dir():
            self.skipTest("the pinned taskboard clone is not on this device")
        table = self.tb.load_zh_hk()
        missing = sorted(set(self.tb.zh_phrases(self.tb.SOURCE)) - set(table))
        self.assertEqual(missing, [], "translate these into Library/taskboard-zh-hk.json")

    def test_check_fails_on_a_planted_untranslated_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.runtime(tmp, {"web/src/App.tsx": 'text("一个从未见过的短语", "Never seen");\n'})
            done = subprocess.run([sys.executable, str(TOOL), "zh-hk", "check"], capture_output=True, text=True,
                                  timeout=60, env=dict(os.environ, DEVARNESS_TASKBOARD_SOURCE=tmp, PYTHONUTF8="1"))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("一个从未见过的短语", done.stdout)


if __name__ == "__main__":
    unittest.main()
