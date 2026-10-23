#!/usr/bin/env python3
"""notify: phone alerts through ntfy when Peter, Aster or May finishes.

Run: python3 Harness/tests/test_notify.py

These tests use invented task names and send nothing: `send` is replaced. They
cover the message format, duration threshold, explicit-report suppression, and
reading each client's turn start from its synthetic transcript.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone

TOOL = Path(__file__).resolve().parents[2] / "Harness" / "bin" / "notify"


def stamp(seconds_ago):
    return datetime.fromtimestamp(time.time() - seconds_ago, timezone.utc).isoformat().replace("+00:00", "Z")


class NotifyTests(unittest.TestCase):
    def setUp(self):
        loader = importlib.machinery.SourceFileLoader("notify", str(TOOL))
        self.mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("notify", loader))
        loader.exec_module(self.mod)
        self.dir = Path(tempfile.mkdtemp())
        self.mod.CONF = self.dir
        self.sent = []
        self.mod.send = lambda kind, agent, message: self.sent.append((kind, agent, message))
        os.environ.pop("DEVARNESS_NOTIFY_MINUTES", None)

    def write(self, name, rows):
        path = self.dir / name
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def hook(self, client, transcript, reply="done"):
        sys.stdin = io.StringIO(json.dumps({"transcript_path": str(transcript), "stop_hook_active": False,
                                            "last_assistant_message": reply}))
        try:
            return self.mod.main(["hook", client])
        finally:
            sys.stdin = sys.__stdin__

    def test_the_done_message_includes_agent_task_and_device(self):
        self.assertEqual(self.mod.task_message("done", "Aster", "Demo_Widget", "the routing report"),
                         'Aster has done the running of "Demo_Widget" on the {} device, '
                         'please review the routing report'.format(self.mod.DEVICE))

    def test_a_long_claude_turn_alerts_as_peter(self):
        t = self.write("claude.jsonl", [
            {"type": "user", "timestamp": stamp(900), "message": {"content": "build it"}},
            {"type": "user", "timestamp": stamp(600), "message": {"content": "<task-notification>x"}},
            {"type": "assistant", "timestamp": stamp(5), "message": {"content": [{"type": "text", "text": "built"}]}}])
        self.assertEqual(self.hook("claude", t), 0)
        self.assertEqual(len(self.sent), 1)
        kind, agent, message = self.sent[0]
        self.assertEqual((kind, agent), ("auto", "Peter"))
        self.assertIn("15-minute run", message)   # from the owner's prompt, not the notification

    def test_a_short_turn_stays_quiet(self):
        t = self.write("claude.jsonl", [{"type": "user", "timestamp": stamp(60), "message": {"content": "hi"}}])
        self.hook("claude", t)
        self.assertEqual(self.sent, [])

    def test_a_long_codex_turn_alerts_as_aster(self):
        t = self.write("rollout.jsonl", [
            {"timestamp": stamp(3600), "type": "event_msg", "payload": {"type": "task_started"}},
            {"timestamp": stamp(720), "type": "event_msg", "payload": {"type": "task_started"}}])
        self.hook("codex", t, reply="routed")
        self.assertEqual([(k, a) for k, a, _ in self.sent], [("auto", "Aster")])
        self.assertIn("12-minute run", self.sent[0][2])   # the last turn, not the session

    def test_a_long_pi_turn_alerts_as_may(self):
        # Pi's session file: each entry is type "message" with the role inside it.
        t = self.write("pi-session.jsonl", [
            {"type": "session", "timestamp": stamp(3600)},
            {"type": "message", "timestamp": stamp(840), "message": {"role": "user", "content": [
                {"type": "text", "text": "design the page"}]}},
            {"type": "message", "timestamp": stamp(5), "message": {"role": "assistant", "content": [
                {"type": "text", "text": "designed"}]}}])
        self.assertEqual(self.hook("pi", t, reply=""), 0)
        self.assertEqual([(k, a) for k, a, _ in self.sent], [("auto", "May")])
        self.assertIn("14-minute run", self.sent[0][2])
        self.assertIn("designed", self.sent[0][2])

    def test_each_client_names_its_agent(self):
        self.assertEqual(self.mod.AGENTS, {"claude": "Peter", "codex": "Aster", "pi": "May"})

    def test_an_explicit_report_suppresses_the_automatic_one(self):
        t = self.write("rollout.jsonl", [{"timestamp": stamp(900), "type": "event_msg",
                                          "payload": {"type": "task_started"}}])
        self.mod.reported("Aster")
        self.hook("codex", t)
        self.assertEqual(self.sent, [])

    def test_one_agents_report_does_not_silence_another(self):
        # Report timestamps must be scoped to each agent, not the whole device.
        t = self.write("rollout.jsonl", [{"timestamp": stamp(900), "type": "event_msg",
                                          "payload": {"type": "task_started"}}])
        self.mod.reported("Peter")
        self.hook("codex", t)
        self.assertEqual([a for _, a, _ in self.sent], ["Aster"])

    def test_a_prompt_sent_as_content_blocks_starts_a_turn(self):
        # A prompt with an image may arrive as content blocks, not a string.
        t = self.write("claude.jsonl", [
            {"type": "user", "timestamp": stamp(1800), "message": {"content": "old prompt"}},
            {"type": "user", "timestamp": stamp(720), "message": {"content": [
                {"type": "text", "text": "look at this"}, {"type": "image", "source": {}}]}},
            {"type": "user", "timestamp": stamp(300), "message": {"content": [
                {"type": "tool_result", "content": "ok"}]}}])
        self.hook("claude", t)
        self.assertIn("12-minute run", self.sent[0][2])

    def test_a_broken_hook_input_never_fails_the_turn(self):
        sys.stdin = io.StringIO("not json")
        try:
            self.assertEqual(self.mod.main(["hook", "claude"]), 0)
        finally:
            sys.stdin = sys.__stdin__

    def test_no_topic_is_a_failure_not_a_silent_pass(self):
        self.mod.TOPIC_FILE = self.dir / "absent"
        os.environ.pop("DEVARNESS_NTFY_TOPIC", None)
        self.assertEqual(self.mod.main(["check"]), 1)

    def test_the_topic_lives_in_the_dev_config_folder(self):
        self.assertEqual(self.mod.TOPIC_FILE, Path.home() / ".config" / "devarness" / "ntfy-topic")


class TopicNeverPrinted(unittest.TestCase):
    """The topic is a key: no command prints it, whether it comes from the file or the
    environment, and whether the send works or fails (ntfy here is a closed port)."""

    def test_no_command_prints_the_topic(self):
        topic = "topic-" + "x7q2k9w4"
        with tempfile.TemporaryDirectory() as home:
            conf = Path(home) / ".config" / "devarness"
            conf.mkdir(parents=True)
            (conf / "ntfy-topic").write_text(topic + "\n", encoding="utf-8")
            base = {k: v for k, v in os.environ.items() if k != "DEVARNESS_NTFY_TOPIC"}
            base.update(HOME=home, USERPROFILE=home, DEVARNESS_NTFY_SERVER="http://127.0.0.1:9", PYTHONIOENCODING="utf-8")
            for env in (base, dict(base, DEVARNESS_NTFY_TOPIC=topic)):
                for args in (["check"], ["test", "May"], ["done", "Peter", "a task", "the report"],
                             ["needs-owner", "Aster", "a task", "a decision"]):
                    done = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                                          encoding="utf-8", env=env, timeout=60)
                    self.assertNotIn(topic, done.stdout + done.stderr, args)
                    self.assertEqual(done.returncode, 0 if args == ["check"] else 1, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
