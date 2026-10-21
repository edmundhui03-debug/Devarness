#!/usr/bin/env python3
"""codex-bridge.mjs, the developer's dashboard's local Codex bridge, on a fake Codex.

Run it with python3 from anywhere; it finds the bridge from its own location.
Design: Library/dashboard/DESIGN.md, whose Codex section lists the routes.
No test spends Codex quota: CODEX_CMD points the bridge at a small
Node script, written per test, that speaks the part of Codex's app-server
protocol the bridge uses. Every process starts without a console window and is
killed in cleanup.
"""
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "Library" / "dashboard" / "codex-bridge.mjs"
NODE = shutil.which("node")
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# SYSTEMDRIVE too: without it each taskkill /T took 2.7 s instead of 0.4 s, measured.
KEEP = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "USERPROFILE", "HOME", "TEMP", "TMP")
KEY_LINE = "Open the dashboard's Codex page and paste this key"
KEY_FILE_LINE = "key written to "

# A fake `codex app-server`: one JSON-RPC message per line on stdin and stdout,
# as Codex's own. It logs every request and every reply it gets to calls.log in
# its working folder and writes its pid to fake.pid. Two threads exist before
# any run: "thread-live", whose session file was written just now, and
# "thread-old", whose file is a day old; a thread it starts gets a file too,
# touched when each turn ends. A prompt containing SLOW starts a turn that waits
# for turn/interrupt; APPROVE asks the bridge for a command approval first;
# EARLY finishes the turn before the start reply, which comes 300 ms later;
# REPLYLATE holds the start reply for 800 ms; NOREPLY never sends it.
FAKE_APP_SERVER = r"""
import { appendFileSync, utimesSync, writeFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { join, resolve } from 'node:path';
writeFileSync('fake.pid', String(process.pid));
const log = (entry) => appendFileSync('calls.log', JSON.stringify(entry) + '\n');
const send = (msg) => process.stdout.write(JSON.stringify(msg) + '\n');
const note = (method, params) => send({ method, params });
for (const [name, age] of [['live.jsonl', 0], ['old.jsonl', 86400]]) {
  writeFileSync(name, '{}\n');
  const t = Date.now() / 1000 - age;
  utimesSync(name, t, t);
}
const thread = (id, extra) => ({
  id, name: null, preview: 'first prompt of ' + id, source: 'cli', cwd: process.cwd(),
  createdAt: 1790000000, updatedAt: 1790000000, status: { type: 'notLoaded' },
  path: null, turns: [], ...extra,
});
const known = new Map([
  ['thread-live', thread('thread-live', { path: resolve('live.jsonl'), updatedAt: 1790000500 })],
  ['thread-old', thread('thread-old', { path: resolve('old.jsonl'), cwd: resolve('..'), preview: 'x'.repeat(500) })],
  ['thread-helper', thread('thread-helper', { agentNickname: 'Volta', updatedAt: 1789000000,
    source: { subAgent: { thread_spawn: { parent_thread_id: 'thread-old', depth: 1, agent_nickname: 'Volta' } } } })],
]);
const loaded = new Set();
let n = 0;
const waiting = new Map();
const LATER = Symbol('later'); // a handler that replies by itself
function finish(threadId, turnId, status) {
  const t = known.get(threadId);
  if (t.path) { const now = Date.now() / 1000; utimesSync(t.path, now, now); }
  note('turn/completed', { threadId, turn: { id: turnId, status, items: [] } });
  t.status = { type: 'idle' };
  note('thread/status/changed', { threadId, status: { type: 'idle' } });
}
const handlers = {
  initialize: () => ({ userAgent: 'fake-codex/1.0', codexHome: '.', platformFamily: 'test', platformOs: 'test' }),
  'thread/list': () => ({ data: [...known.values()].map((t) => ({ ...t, status: loaded.has(t.id) ? t.status : { type: 'notLoaded' } })) }),
  'thread/loaded/list': () => ({ data: [...loaded] }),
  'thread/read': ({ threadId }) => {
    if (!known.has(threadId)) throw { code: -32602, message: 'thread not loaded: ' + threadId };
    const turns = Array.from({ length: 25 }, (_, i) => ({
      id: 'turn-' + i, status: 'completed', startedAt: 1790000000 + i, completedAt: 1790000001 + i, items: [
        { type: 'userMessage', id: 'u' + i, content: [{ type: 'text', text: 'question ' + i }] },
        { type: 'commandExecution', id: 'c' + i, command: 'ls', status: 'completed', exitCode: 0, aggregatedOutput: 'y'.repeat(9000) },
        { type: 'agentMessage', id: 'a' + i, text: 'answer ' + i },
      ] }));
    return { thread: { ...known.get(threadId), turns } };
  },
  'thread/start': (params) => {
    const id = 'thread-new-' + (++n);
    writeFileSync(id + '.jsonl', '{}\n');
    const t = thread(id, { cwd: params.cwd, status: { type: 'idle' }, path: resolve(id + '.jsonl') });
    known.set(t.id, t); loaded.add(t.id);
    note('thread/started', { thread: t });
    return { thread: t };
  },
  'thread/resume': ({ threadId }) => {
    if (!known.has(threadId)) throw { code: -32602, message: 'thread not loaded: ' + threadId };
    loaded.add(threadId); known.get(threadId).status = { type: 'idle' };
    return { thread: known.get(threadId) };
  },
  'turn/start': ({ threadId, input }, id) => {
    const turnId = 'turn-' + (++n);
    const text = input.map((i) => i.text).join(' ');
    const start = () => {
      known.get(threadId).status = { type: 'active', activeFlags: [] };
      note('thread/status/changed', { threadId, status: { type: 'active', activeFlags: [] } });
      note('turn/started', { threadId, turn: { id: turnId, status: 'inProgress', items: [] } });
      if (text.includes('APPROVE')) send({ id: 'srv-1', method: 'item/commandExecution/requestApproval', params: { threadId, turnId, command: 'rm -rf /' } });
      if (text.includes('SLOW') || text.includes('NOREPLY')) { waiting.set(turnId, threadId); return; }
      note('item/completed', { threadId, turnId, item: { type: 'agentMessage', id: 'm' + n, text: 'hello from the fake' } });
      finish(threadId, turnId, 'completed');
    };
    const reply = () => send({ id, result: { turn: { id: turnId, status: 'inProgress', items: [] } } });
    if (text.includes('EARLY')) { start(); setTimeout(reply, 300); }
    else if (text.includes('NOREPLY')) setTimeout(start, 20);
    else { setTimeout(reply, text.includes('REPLYLATE') ? 800 : 0); setTimeout(start, 20); }
    return LATER;
  },
  'turn/interrupt': ({ threadId, turnId }) => {
    if (waiting.delete(turnId)) setTimeout(() => finish(threadId, turnId, 'interrupted'), 20);
    return {};
  },
  'account/read': () => ({ account: { type: 'chatgpt', email: 'secret-owner@example.com', planType: 'plus' }, requiresOpenaiAuth: true }),
  'account/rateLimits/read': () => ({ rateLimits: { primary: { usedPercent: 40, windowDurationMins: 10080, resetsAt: 1900000000 }, secondary: null } }),
  'account/login/start': () => {
    setTimeout(() => note('account/login/completed', { loginId: 'login-1', success: true }), 50);
    return { type: 'chatgpt', loginId: 'login-1', authUrl: 'https://auth.openai.com/oauth/authorize?fake=1' };
  },
};
createInterface({ input: process.stdin }).on('line', (line) => {
  const msg = JSON.parse(line);
  log(msg);
  if (msg.method === undefined || msg.id === undefined) return; // a reply or a notification
  const handler = handlers[msg.method];
  try {
    if (!handler) throw { code: -32601, message: 'unknown method ' + msg.method };
    const result = handler(msg.params ?? {}, msg.id);
    if (result !== LATER) send({ id: msg.id, result });
  } catch (err) {
    send({ id: msg.id, error: { code: err.code ?? -32603, message: err.message ?? String(err) } });
  }
});
"""


def small_env():
    """A small environment of its own for each child, never the whole one (LESSONS.md:460)."""
    return {key: os.environ[key] for key in KEEP if key in os.environ}


def kill_pid(pid):
    """End one process by id, quietly; it may already be gone."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True,
                       env=small_env(), creationflags=HIDDEN)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def alive(pid):
    # Node's kill(pid, 0) only asks; Python's os.kill(pid, 0) on Windows kills.
    probe = f"try {{ process.kill({int(pid)}, 0) }} catch {{ process.exit(1) }}"
    return subprocess.run([NODE, "-e", probe], capture_output=True,
                          env=small_env(), creationflags=HIDDEN).returncode == 0


@unittest.skipUnless(NODE, "node is not on PATH")
class BridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fake = root / "fake-app-server.mjs"
        fake.write_text(FAKE_APP_SERVER, encoding="utf-8")
        self.codex_cmd = [NODE, str(fake)]
        self.folder = root / "work"
        self.folder.mkdir()
        self.lines = []
        self.proc = self.start_bridge("--port", "0")
        self.addCleanup(self.stop_bridge)
        self.port, self.key = self.wait_ready()

    # --- the bridge process -------------------------------------------------

    def start_bridge(self, *args, env=None):
        env = dict(small_env(), CODEX_CMD=json.dumps(self.codex_cmd), **(env or {}))
        proc = subprocess.Popen(
            [NODE, str(BRIDGE), "--folder", str(self.folder), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=env, text=True, encoding="utf-8",
            errors="replace", creationflags=HIDDEN)
        self.reader = threading.Thread(target=self.read_output, args=(proc,),
                                       daemon=True)
        self.reader.start()
        return proc

    def read_output(self, proc):
        for line in proc.stdout:
            self.lines.append(line.rstrip("\n"))

    def wait_ready(self, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            lines = list(self.lines)
            for i, line in enumerate(lines[:-1]):
                if line.startswith(KEY_LINE):
                    port = re.search(r"http://127\.0\.0\.1:(\d+)", "\n".join(lines))
                    self.assertIsNotNone(port, "the bridge printed no address")
                    return int(port.group(1)), lines[i + 1].strip()
            if self.proc.poll() is not None:
                break
            time.sleep(0.05)
        self.fail("the bridge did not start:\n" + "\n".join(self.lines))

    def stop_bridge(self):
        if self.proc.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)],
                               capture_output=True, env=small_env(), creationflags=HIDDEN)
            else:
                self.proc.terminate()  # the bridge ends Codex's tree itself
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(10)
        self.reader.join(5)
        self.proc.stdout.close()

    # --- HTTP ---------------------------------------------------------------

    def request(self, method, path, body=None, key="", headers=None, raw=None):
        """One request; key="" means the right key, None means no key at all."""
        sent = {} if key is None else {"X-Bridge-Key": self.key if key == "" else key}
        data = raw
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            sent["Content-Type"] = "application/json"
        sent.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=data, headers=sent)
            resp = conn.getresponse()
            text = resp.read().decode("utf-8")
        finally:
            conn.close()
        is_json = resp.headers.get_content_type() == "application/json"
        return resp.status, resp.headers, json.loads(text) if is_json else text

    def run_codex(self, prompt, thread=None, sandbox="read-only"):
        status, _, reply = self.request(
            "POST", "/run", {"prompt": prompt, "sandbox": sandbox, "thread": thread})
        self.assertEqual(status, 200, reply)
        return reply

    def open_events(self):
        """Open the event stream; return (connection, a generator of events)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        conn.request("GET", "/events", headers={"Origin": "null", "X-Bridge-Key": self.key})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.headers["Access-Control-Allow-Origin"], "null")
        self.assertTrue(resp.headers["Content-Type"].startswith("text/event-stream"))

        def events():
            for raw in resp:
                line = raw.decode("utf-8").rstrip("\r\n")
                if line.startswith("data: "):
                    yield json.loads(line[len("data: "):])
        return events()

    @staticmethod
    def until(stream, method, **match):
        """Read events until one with this method whose params hold every match."""
        seen = []
        for event in stream:
            seen.append(event)
            params = event.get("params") or {}
            if event["method"] == method and all(params.get(k) == v for k, v in match.items()):
                return event, seen
        raise AssertionError(f"the stream ended before {method}: {seen}")

    def calls(self, method=None):
        log = self.folder / "calls.log"
        if not log.exists():
            return []
        entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        return [e for e in entries if method is None or e.get("method") == method]

    # --- the key ------------------------------------------------------------

    def test_a_request_without_the_key_is_refused_and_runs_nothing(self):
        body = {"prompt": "hello", "sandbox": "read-only", "thread": None}
        for method, path, sent in (("GET", "/health", None), ("GET", "/threads", None),
                                   ("GET", "/account", None), ("POST", "/run", body),
                                   ("POST", "/login", {}), ("GET", "/events", None)):
            self.assertEqual(self.request(method, path, sent, key=None)[0], 401, path)
        self.assertEqual(self.calls("turn/start"), [])
        self.assertEqual(self.calls("account/login/start"), [])

    def test_a_wrong_key_is_refused_and_runs_nothing(self):
        body = {"prompt": "hello", "sandbox": "read-only", "thread": None}
        same_length = ("A" if self.key[0] != "A" else "B") + self.key[1:]
        for wrong in (same_length, "short", self.key + "x"):
            self.assertEqual(self.request("POST", "/run", body, key=wrong)[0], 401)
            self.assertEqual(self.request("GET", "/health", key=wrong)[0], 401)
        self.assertEqual(self.calls("turn/start"), [])

    def test_the_event_stream_takes_the_key_only_in_its_header(self):
        # A key in the address ends up in logs and history; the page sends a header.
        status, _, _ = self.request("GET", f"/events?key={quote(self.key)}", key=None)
        self.assertEqual(status, 401)

    def test_the_key_is_random_and_printed_only_once(self):
        self.assertRegex(self.key, r"^[A-Za-z0-9_-]{32}$")  # 24 bytes, base64url
        self.run_codex("hello")
        self.stop_bridge()
        self.assertEqual("\n".join(self.lines).count(self.key), 1)
        self.assertFalse(any(line.startswith(KEY_FILE_LINE) for line in self.lines))

    def restart_with(self, *args, env=None):
        """Start the bridge again with more arguments; return once it is ready."""
        self.stop_bridge()
        self.lines = []
        self.proc = self.start_bridge("--port", "0", *args, env=env)
        self.port, self.key = self.wait_ready()

    def restart_with_key_file(self, key_file):
        """Start the bridge again with --key-file; wait until it says where the key is."""
        self.stop_bridge()
        self.lines = []
        self.proc = self.start_bridge("--port", "0", "--key-file", str(key_file))
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and self.proc.poll() is None:
            written = [line for line in self.lines if line.startswith(KEY_FILE_LINE)]
            if written:
                port = re.search(r"http://127\.0\.0\.1:(\d+)", "\n".join(self.lines))
                return int(port.group(1)), written[0][len(KEY_FILE_LINE):]
            time.sleep(0.05)
        return None, None

    def test_a_key_file_gets_the_key_and_the_output_never_shows_it(self):
        key_file = self.folder.parent / "bridge.key"
        self.port, said = self.restart_with_key_file(key_file)
        self.assertIsNotNone(said, "\n".join(self.lines))
        self.assertTrue(os.path.samefile(said, key_file))
        self.key = key_file.read_text(encoding="utf-8").strip()
        self.assertRegex(self.key, r"^[A-Za-z0-9_-]{32}$")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(key_file.stat().st_mode), 0o600)
        self.assertEqual(self.request("GET", "/health")[0], 200)
        self.run_codex("hello")
        self.stop_bridge()
        self.assertNotIn(self.key, "\n".join(self.lines))
        self.assertFalse(any(line.startswith(KEY_LINE) for line in self.lines))

    def test_a_key_file_that_already_exists_is_never_overwritten(self):
        key_file = self.folder.parent / "bridge.key"
        key_file.write_text("someone else's file\n", encoding="utf-8")
        port, said = self.restart_with_key_file(key_file)
        self.assertIsNone(said, "\n".join(self.lines))
        self.assertEqual(self.proc.wait(10), 2)
        self.assertEqual(key_file.read_text(encoding="utf-8"), "someone else's file\n")
        self.assertFalse(any(line.startswith(KEY_LINE) for line in self.lines))

    # --- health and the account ---------------------------------------------

    def test_health_names_the_folder_the_codex_command_and_the_app_server(self):
        status, _, health = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertIs(health["ok"], True)
        self.assertTrue(os.path.samefile(health["folder"], self.folder))
        self.assertIn("fake-app-server.mjs", health["codex"])
        self.assertEqual(health["appServer"], {"up": True, "userAgent": "fake-codex/1.0"})
        init = self.calls("initialize")
        self.assertEqual(len(init), 1)
        self.assertEqual(init[0]["params"]["clientInfo"]["name"], "dev-dashboard-bridge")
        self.assertEqual(len(self.calls("initialized")), 1)

    def test_an_app_server_that_cannot_start_is_reported_not_fatal(self):
        self.codex_cmd = [str(self.folder / "no-such-codex.exe")]
        self.restart_with()
        status, _, health = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertIs(health["appServer"]["up"], False)
        self.assertTrue(health["appServer"]["error"])
        status, _, reply = self.request(
            "POST", "/run", {"prompt": "hi", "sandbox": "read-only", "thread": None})
        self.assertEqual(status, 502, reply)
        self.assertIn("error", reply)

    def test_the_account_says_signed_in_and_the_quota_but_never_the_email(self):
        status, _, account = self.request("GET", "/account")
        self.assertEqual(status, 200)
        self.assertEqual(account["signedIn"], True)
        self.assertEqual(account["type"], "chatgpt")
        self.assertEqual(account["plan"], "plus")
        self.assertEqual(account["rateLimits"]["primary"]["usedPercent"], 40)
        self.assertIsNone(account["rateLimits"]["secondary"])
        self.assertNotIn("secret-owner", json.dumps(account))

    def test_login_starts_a_chatgpt_sign_in_and_reports_when_it_finishes(self):
        stream = self.open_events()
        status, _, reply = self.request("POST", "/login", {})
        self.assertEqual(status, 200, reply)
        self.assertEqual(reply, {"authUrl": "https://auth.openai.com/oauth/authorize?fake=1",
                                 "loginId": "login-1"})
        self.assertEqual(self.calls("account/login/start")[0]["params"], {"type": "chatgpt"})
        event, _ = self.until(stream, "account/login/completed")
        self.assertIs(event["params"]["success"], True)

    # --- threads ------------------------------------------------------------

    def test_the_thread_list_asks_for_every_source_and_marks_what_runs(self):
        status, _, reply = self.request("GET", "/threads")
        self.assertEqual(status, 200, reply)
        params = self.calls("thread/list")[0]["params"]
        # Codex leaves `codex exec` runs out unless asked: Aster's runs are exec runs.
        self.assertIn("exec", params["sourceKinds"])
        self.assertIn("cli", params["sourceKinds"])
        threads = {t["id"]: t for t in reply["threads"]}
        self.assertEqual(threads["thread-live"]["state"], "active-elsewhere")
        self.assertEqual(threads["thread-old"]["state"], "idle")
        self.assertEqual(reply["threads"][0]["id"], "thread-live")  # running first
        self.assertLessEqual(len(threads["thread-old"]["preview"]), 200)
        self.assertNotIn("turns", threads["thread-old"])
        helper = threads["thread-helper"]
        self.assertEqual((helper["source"], helper["nickname"]), ("subAgent", "Volta"))

    def test_a_thread_shows_its_last_twenty_turns_with_long_text_clipped(self):
        status, _, thread = self.request("GET", "/thread?id=thread-old")
        self.assertEqual(status, 200, thread)
        self.assertEqual(len(thread["turns"]), 20)
        self.assertEqual(thread["turns"][-1]["id"], "turn-24")
        out = thread["turns"][-1]["items"][1]["aggregatedOutput"]
        # Command output keeps its end, where a test or build summary sits.
        self.assertLessEqual(len(out), 4001)
        self.assertTrue(out.startswith("…"))
        self.assertEqual(self.request("GET", "/thread?id=nope")[0], 404)
        self.assertEqual(self.request("GET", "/thread")[0], 400)

    # --- runs ---------------------------------------------------------------

    def test_a_new_run_starts_a_thread_in_the_folder_and_streams_its_turn(self):
        stream = self.open_events()
        reply = self.run_codex("hello")
        thread, turn = reply["thread"], reply["turn"]
        start = self.calls("thread/start")[0]["params"]
        self.assertTrue(os.path.samefile(start["cwd"], self.folder))
        self.assertEqual(start["sandbox"], "read-only")
        self.assertEqual(start["approvalPolicy"], "never")
        turn_start = self.calls("turn/start")[0]["params"]
        self.assertEqual(turn_start["threadId"], thread)
        self.assertEqual(turn_start["input"], [{"type": "text", "text": "hello"}])
        self.assertEqual(turn_start["sandboxPolicy"], {"type": "readOnly"})
        self.assertNotIn("danger", json.dumps(self.calls()))
        _, seen = self.until(stream, "turn/completed", threadId=thread)
        methods = [e["method"] for e in seen if (e.get("params") or {}).get("threadId") == thread]
        self.assertIn("turn/started", methods)
        message = next(e for e in seen if e["method"] == "item/completed")
        self.assertEqual(message["params"]["item"]["text"], "hello from the fake")
        self.assertEqual(seen[-1]["params"]["turn"]["id"], turn)
        _, _, listed = self.request("GET", "/threads")
        mine = next(t for t in listed["threads"] if t["id"] == thread)
        self.assertEqual(mine["state"], "idle")

    def test_a_run_can_continue_a_thread_from_the_list(self):
        reply = self.run_codex("again", thread="thread-old")
        self.assertEqual(reply["thread"], "thread-old")
        self.assertEqual(self.calls("thread/resume")[0]["params"]["threadId"], "thread-old")
        self.assertEqual(self.calls("thread/start"), [])

    def test_a_thread_running_elsewhere_is_not_continued(self):
        body = {"prompt": "x", "sandbox": "read-only", "thread": "thread-live"}
        self.assertEqual(self.request("POST", "/run", body)[0], 409)
        self.assertEqual(self.calls("turn/start"), [])

    def test_writing_is_offered_only_in_the_bridges_own_folder(self):
        # thread-old works in another folder: it may be continued read-only only.
        body = {"prompt": "x", "sandbox": "workspace-write", "thread": "thread-old"}
        self.assertEqual(self.request("POST", "/run", body)[0], 403)
        self.assertEqual(self.calls("turn/start"), [])
        reply = self.run_codex("write here", sandbox="workspace-write")
        policy = self.calls("turn/start")[0]["params"]["sandboxPolicy"]
        # Codex's defaults would also let the turn write to the temporary folders.
        self.assertEqual(policy, {"type": "workspaceWrite", "writableRoots": [], "networkAccess": False,
                                  "excludeSlashTmp": True, "excludeTmpdirEnvVar": True})
        self.assertEqual(self.calls("thread/start")[0]["params"]["sandbox"], "workspace-write")
        self.assertTrue(reply["thread"])

    def test_a_thread_runs_one_turn_at_a_time_and_stop_interrupts_it(self):
        stream = self.open_events()
        reply = self.run_codex("SLOW please")
        thread, turn = reply["thread"], reply["turn"]
        self.until(stream, "turn/started", threadId=thread)
        _, _, listed = self.request("GET", "/threads")
        self.assertEqual(next(t for t in listed["threads"] if t["id"] == thread)["state"], "running")
        body = {"prompt": "again", "sandbox": "read-only", "thread": thread}
        self.assertEqual(self.request("POST", "/run", body)[0], 409)
        status, _, stopped = self.request("POST", "/stop", {"thread": thread, "turn": turn})
        self.assertEqual(status, 200, stopped)
        self.assertEqual(self.calls("turn/interrupt")[0]["params"],
                         {"threadId": thread, "turnId": turn})
        event, _ = self.until(stream, "turn/completed", threadId=thread)
        self.assertEqual(event["params"]["turn"]["status"], "interrupted")
        self.assertEqual(len(self.calls("turn/start")), 1)

    def test_a_late_start_reply_never_takes_over_the_next_turn(self):
        stream = self.open_events()
        thread = self.run_codex("hello")["thread"]
        self.until(stream, "turn/completed", threadId=thread)
        replies = {}
        early = threading.Thread(target=lambda: replies.setdefault("a", self.request(
            "POST", "/run", {"prompt": "EARLY", "sandbox": "read-only", "thread": thread})))
        early.start()
        self.until(stream, "turn/completed", threadId=thread)  # before its start reply
        status, _, late = self.request(
            "POST", "/run", {"prompt": "SLOW REPLYLATE", "sandbox": "read-only", "thread": thread})
        early.join(10)
        self.assertEqual(status, 200, late)
        self.assertEqual(replies["a"][0], 200, replies["a"])
        status, _, stopped = self.request("POST", "/stop", {"thread": thread, "turn": late["turn"]})
        self.assertEqual(status, 200, stopped)

    def test_a_start_codex_never_confirms_keeps_the_thread_busy_and_stoppable(self):
        self.restart_with(env={"CODEX_BRIDGE_TIMEOUT_MS": "1000"})
        stream = self.open_events()
        thread = self.run_codex("hello")["thread"]
        self.until(stream, "turn/completed", threadId=thread)
        status, _, reply = self.request(
            "POST", "/run", {"prompt": "NOREPLY", "sandbox": "read-only", "thread": thread})
        self.assertEqual(status, 504, reply)
        started, _ = self.until(stream, "turn/started", threadId=thread)
        turn = started["params"]["turn"]["id"]
        # The turn may well be running: the thread stays busy and its turn can be stopped.
        body = {"prompt": "again", "sandbox": "read-only", "thread": thread}
        self.assertEqual(self.request("POST", "/run", body)[0], 409)
        self.assertEqual(self.request("POST", "/stop", {"thread": thread, "turn": turn})[0], 200)

    def test_a_thread_changed_elsewhere_after_this_bridge_used_it_is_not_continued(self):
        stream = self.open_events()
        thread = self.run_codex("hello")["thread"]
        self.until(stream, "turn/completed", threadId=thread)
        _, _, listed = self.request("GET", "/threads")
        self.assertEqual(next(t for t in listed["threads"] if t["id"] == thread)["state"], "idle")
        time.sleep(1.5)
        os.utime(self.folder / (thread + ".jsonl"))  # another Codex window writes to it
        _, _, listed = self.request("GET", "/threads")
        self.assertEqual(next(t for t in listed["threads"] if t["id"] == thread)["state"],
                         "active-elsewhere")
        body = {"prompt": "x", "sandbox": "read-only", "thread": thread}
        self.assertEqual(self.request("POST", "/run", body)[0], 409)

    def test_stop_refuses_a_turn_this_bridge_is_not_running(self):
        body = {"thread": "thread-old", "turn": "nope"}
        self.assertEqual(self.request("POST", "/stop", body)[0], 404)
        self.assertEqual(self.calls("turn/interrupt"), [])

    def test_an_approval_codex_asks_for_is_declined_and_shown(self):
        stream = self.open_events()
        reply = self.run_codex("APPROVE and SLOW")
        event, _ = self.until(stream, "bridge/declined")
        self.assertEqual(event["params"]["request"], "item/commandExecution/requestApproval")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            answers = [c for c in self.calls() if c.get("id") == "srv-1"]
            if answers:
                break
            time.sleep(0.05)
        self.assertEqual(len(answers), 1)
        self.assertIn("error", answers[0])
        self.request("POST", "/stop", {"thread": reply["thread"], "turn": reply["turn"]})

    def test_closing_the_bridge_ends_the_app_server(self):
        self.request("GET", "/health")
        pid = int((self.folder / "fake.pid").read_text())
        self.addCleanup(kill_pid, pid)
        self.assertTrue(alive(pid))
        # Only the bridge is ended, never its tree: on Windows its children die
        # with it (libuv's kill-on-close job); elsewhere it ends them on SIGTERM.
        if os.name == "nt":
            kill_pid(self.proc.pid)
        else:
            self.proc.terminate()
        self.proc.wait(10)
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(alive(pid), "the app-server outlived the bridge")

    # --- what a run may ask for ---------------------------------------------

    def test_a_sandbox_other_than_the_two_offered_is_refused(self):
        for sandbox in ("danger-full-access", "", None, "READ-ONLY"):
            body = {"prompt": "hello", "sandbox": sandbox, "thread": None}
            self.assertEqual(self.request("POST", "/run", body)[0], 400, sandbox)
        self.assertEqual(self.request("POST", "/run", {"prompt": "hello"})[0], 400)
        self.assertEqual(self.calls("turn/start"), [])

    def test_a_run_needs_a_prompt_and_a_thread_id_is_a_string(self):
        for prompt in ("", "   ", None, 7):
            body = {"prompt": prompt, "sandbox": "read-only", "thread": None}
            self.assertEqual(self.request("POST", "/run", body)[0], 400, prompt)
        for thread in (7, "", ["x"]):
            body = {"prompt": "x", "sandbox": "read-only", "thread": thread}
            self.assertEqual(self.request("POST", "/run", body)[0], 400, thread)
        self.assertEqual(self.calls("turn/start"), [])

    def test_bodies_are_json_and_at_most_64_kib(self):
        big = json.dumps({"prompt": "x" * (65 * 1024), "sandbox": "read-only"})
        json_type = {"Content-Type": "application/json"}
        self.assertEqual(self.request("POST", "/run", raw=big.encode(),
                                      headers=json_type)[0], 413)
        self.assertEqual(self.request("POST", "/run", raw=b"{not json",
                                      headers=json_type)[0], 400)
        self.assertEqual(self.request("POST", "/run", raw=b"[1, 2]",
                                      headers=json_type)[0], 400)
        plain = json.dumps({"prompt": "x", "sandbox": "read-only"}).encode()
        self.assertEqual(self.request("POST", "/run", raw=plain,
                                      headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.calls("turn/start"), [])

    def test_a_malformed_request_target_is_refused_without_stopping_the_bridge(self):
        # Node accepts this absolute-form target; the URL parser does not.
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as conn:
            conn.sendall(b"GET http://[x/health HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                         b"Connection: close\r\n\r\n")
            reply = conn.recv(100)
        self.assertTrue(reply.startswith(b"HTTP/1.1 4"), reply)
        self.assertEqual(self.request("GET", "/health")[0], 200)

    # --- the browser's view: CORS -------------------------------------------

    def test_cors_allows_a_page_from_disk_the_bridge_and_named_loopback_pages(self):
        self.restart_with("--allow-origin", "http://127.0.0.1:5173")
        own = f"http://127.0.0.1:{self.port}"
        preflight = {"Access-Control-Request-Method": "POST",
                     "Access-Control-Request-Headers": "content-type,x-bridge-key"}
        for origin in ("null", own, "http://127.0.0.1:5173"):
            status, headers, _ = self.request(
                "OPTIONS", "/run", key=None, headers=dict(preflight, Origin=origin))
            self.assertEqual(status, 204)
            self.assertEqual(headers["Access-Control-Allow-Origin"], origin)
            self.assertIn("x-bridge-key",
                          headers["Access-Control-Allow-Headers"].lower())
            status, headers, _ = self.request("GET", "/health",
                                              headers={"Origin": origin})
            self.assertEqual(status, 200)
            self.assertEqual(headers["Access-Control-Allow-Origin"], origin)
        # A refused key still reaches the page, so it can say "wrong key".
        status, headers, _ = self.request("GET", "/health", key="wrong",
                                          headers={"Origin": "null"})
        self.assertEqual(status, 401)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "null")
        for origin in ("http://evil.example", "http://localhost:3000",
                       "http://127.0.0.1:5174"):
            status, headers, _ = self.request(
                "OPTIONS", "/run", key=None, headers=dict(preflight, Origin=origin))
            self.assertNotEqual(status, 204)
            self.assertIsNone(headers["Access-Control-Allow-Origin"])
            body = {"prompt": "hello", "sandbox": "read-only", "thread": None}
            status, headers, _ = self.request("POST", "/run", body,
                                              headers={"Origin": origin})
            self.assertEqual(status, 403)
            self.assertIsNone(headers["Access-Control-Allow-Origin"])
        self.assertEqual(self.calls("turn/start"), [])

    def test_a_foreign_host_is_refused_even_with_the_key(self):
        # A site that rebinds its own name to 127.0.0.1 sends its own Host and no Origin.
        for host in (f"attacker.example:{self.port}", f"localhost:{self.port}", "127.0.0.1"):
            self.assertEqual(self.request("GET", "/health", headers={"Host": host})[0], 403, host)
            preflight = {"Host": host, "Origin": "null", "Access-Control-Request-Method": "POST"}
            self.assertEqual(self.request("OPTIONS", "/run", key=None, headers=preflight)[0], 403, host)
        self.assertEqual(self.calls("initialize"), [])

    def test_an_allowed_origin_must_be_a_loopback_page(self):
        env = dict(small_env(), CODEX_CMD=json.dumps(self.codex_cmd))
        for origin in ("http://evil.example", "http://localhost:5173", "null",
                       "http://127.0.0.1:5173/", "https://127.0.0.1:5173",
                       "http://127.0.0.1:99999", "http://127.0.0.1:05173", "http://127.0.0.1:80"):
            refused = subprocess.run(
                [NODE, str(BRIDGE), "--folder", str(self.folder), "--port", "0",
                 "--allow-origin", origin],
                capture_output=True, text=True, env=env, timeout=30,
                stdin=subprocess.DEVNULL, creationflags=HIDDEN)
            self.assertEqual(refused.returncode, 2, origin)
            self.assertNotIn(KEY_LINE, refused.stdout)

    # --- where it listens ---------------------------------------------------

    def test_it_listens_on_loopback_and_refuses_any_other_host(self):
        self.assertTrue(any(f"http://127.0.0.1:{self.port}" in line
                            for line in self.lines))
        env = dict(small_env(), CODEX_CMD=json.dumps(self.codex_cmd))
        for host in ("0.0.0.0", "localhost", "::"):
            refused = subprocess.run(
                [NODE, str(BRIDGE), "--folder", str(self.folder), "--host", host,
                 "--port", "0"],
                capture_output=True, text=True, env=env, timeout=30,
                stdin=subprocess.DEVNULL, creationflags=HIDDEN)
            self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
            self.assertIn("127.0.0.1", refused.stderr)
            self.assertNotIn(KEY_LINE, refused.stdout)

    def test_a_missing_folder_or_bad_codex_command_is_refused(self):
        env = dict(small_env(), CODEX_CMD=json.dumps(self.codex_cmd))
        missing = self.folder / "missing"
        cases = [
            ([], env),
            (["--folder", str(missing)], env),
            (["--folder", str(self.folder), "--port", "http"], env),
            (["--folder", str(self.folder)], dict(env, CODEX_CMD="codex --yolo")),
            (["--folder", str(self.folder)], dict(env, CODEX_CMD="[]")),
        ]
        for args, case_env in cases:
            refused = subprocess.run(
                [NODE, str(BRIDGE), *args], capture_output=True, text=True,
                env=case_env, timeout=30, stdin=subprocess.DEVNULL,
                creationflags=HIDDEN)
            self.assertEqual(refused.returncode, 2, args)
            self.assertNotIn(KEY_LINE, refused.stdout)


if __name__ == "__main__":
    unittest.main()
