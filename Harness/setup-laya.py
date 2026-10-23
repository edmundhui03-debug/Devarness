#!/usr/bin/env python3
"""Install pinned laya in the Library's ignored runtime, and check the service and the tool the agents run.

  python3 Harness/setup-laya.py --install            venv, CPU torch, laya at the pin, the weights,
                                                 then the service restarted on the new code
  python3 Harness/setup-laya.py --check [--predict]  the MCP tool lists its tools and ends on EOF, the
                                                 service answers, the evaluation clears its gate;
                                                 --predict also answers one question through MCP

Harness/bin/laya-service is the tool: the MCP server both agents start, and the
service it talks to. The weights come from Hugging Face here, at install, and
never during a session. update-tools runs --install when the pin moves and
--check after it, so a release that decides worse than the gate rolls back.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

LIBRARY = Path(__file__).resolve().parent
RUNTIME = LIBRARY / ".runtime" / "laya"
PYTHON = RUNTIME / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
LAUNCHER = LIBRARY / "bin" / "laya-service"
WEIGHTS = "convaiinnovations/laya"      # one repo holds all three checkpoints the router picks from
FILES = ["rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*"]
TOOLS = {"laya_decide", "laya_predict", "laya_status"}


def pin() -> str:
    for line in (LIBRARY / "repos.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("Harness/laya\t"):
            return line.split("\t")[2]
    raise SystemExit("Harness/laya is not in Harness/repos.txt")


def run(*args, env=None):
    subprocess.run([str(a) for a in args], check=True, env=env)


def install() -> int:
    sha = pin()
    head = subprocess.run(["git", "-C", str(LIBRARY / "laya"), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    if head != sha:
        raise SystemExit("Harness/laya is at %s, its pin is %s: update-tools apply first" % (head[:7], sha[:7]))
    if os.name == "nt":
        # The running service holds its files open, and an install cannot replace them.
        subprocess.run(["schtasks", "/End", "/TN", "DEVARNESS_laya_serve"], capture_output=True)
        time.sleep(2)
    if not PYTHON.is_file():
        run("uv", "venv", "--python", "3.12", PYTHON.parents[1])
    # CPU wheels: a tenth of CUDA's download, and a call is one forward pass.
    run("uv", "pip", "install", "--python", PYTHON, "--index-url", "https://download.pytorch.org/whl/cpu", "torch")
    with tempfile.TemporaryDirectory() as tmp:
        # The reviewed bytes, exported, so a build never writes into the clone.
        archive = Path(tmp) / "laya.tar"
        with archive.open("wb") as out:
            subprocess.run(["git", "-C", str(LIBRARY / "laya"), "archive", sha], stdout=out, check=True)
        with tarfile.open(archive) as tar:
            # The Mac's python3 is 3.9, which has no filter; git archive of the
            # pin cannot hold an absolute or ../ path, so nothing is lost there.
            if hasattr(tarfile, "data_filter"):
                tar.extractall(Path(tmp) / "src", filter="data")
            else:
                tar.extractall(Path(tmp) / "src")
        run("uv", "pip", "install", "--python", PYTHON, "laya[mcp,serve] @ " + (Path(tmp) / "src").as_uri())
    env = dict(os.environ, HF_HOME=str(RUNTIME / "hf"), HF_HUB_DISABLE_TELEMETRY="1")
    patterns = [prefix + name for prefix in ("", "multilingual/", "typed-decisions/") for name in FILES]
    run(PYTHON, "-c", "from huggingface_hub import snapshot_download as get; "
                      "print('weights at', get(%r, allow_patterns=%r))" % (WEIGHTS, patterns), env=env)
    (RUNTIME / "install.json").write_text(json.dumps(
        {"pin": sha, "installed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2) + "\n",
        encoding="utf-8")
    run(sys.executable, LAUNCHER, "install-service")      # registers it where it is new, and starts it
    return check(predict=True)


class Server:
    """The launcher over stdio, as an agent's client starts it."""

    def __init__(self):
        self.log = (RUNTIME / "check.log").open("w", encoding="utf-8")     # the server's stderr
        self.process = subprocess.Popen([sys.executable, str(LAUNCHER)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.log,
                                        text=True, encoding="utf-8")
        self.lines = queue.Queue()
        threading.Thread(target=lambda: [self.lines.put(l) for l in self.process.stdout], daemon=True).start()

    def call(self, ident, method, params, timeout):
        self.send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                message = json.loads(self.lines.get(timeout=max(0.1, end - time.monotonic())))
            except queue.Empty:
                break
            if message.get("id") == ident:
                return message
        raise TimeoutError("%s gave no answer in %d s" % (method, timeout))

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()


def check(predict: bool = False) -> int:
    if not PYTHON.is_file():
        print("laya: not installed; python3 Harness/setup-laya.py --install")
        return 1
    started = time.monotonic()
    server = Server()
    try:
        server.call(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "setup-laya", "version": "1"}}, 120)
        server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        names = {t["name"] for t in server.call(2, "tools/list", {}, 60)["result"]["tools"]}
        if not TOOLS <= names:
            print("laya: tools missing: %s" % sorted(TOOLS - names))
            return 1
        print("laya: MCP server ready in %.1f s with %s" % (time.monotonic() - started, ", ".join(sorted(names))))
        if predict:
            reply = server.call(3, "tools/call", {"name": "laya_decide", "arguments": {
                "kind": "failure", "text": "The sync stopped on a rebase conflict and nothing was pushed today."}}, 600)
            print("laya: answered through MCP: %s" % reply["result"]["content"][0]["text"][:300])
    finally:
        server.process.stdin.close()            # what a client does when its session ends
        try:
            server.process.wait(timeout=20)
            ended = True
        except subprocess.TimeoutExpired:
            server.process.kill()
            ended = False
    print("laya: ended on end of input" if ended else "laya: did not end on end of input; killed")
    if not ended:
        return 1
    # The gate that decides whether an update stays: the dev evaluation set,
    # answered by the service the agents use.
    return subprocess.run([sys.executable, str(LAUNCHER), "eval", "--gate"]).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--predict", action="store_true", help="with --check: answer one question")
    args = parser.parse_args()
    return install() if args.install else check(args.predict)


if __name__ == "__main__":
    sys.exit(main())
