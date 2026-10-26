#!/usr/bin/env python3
"""Check or explicitly record trust for this checkout's Codex hooks.

    python3 Harness/codex-hook-trust.py --check          # 0 all trusted, 1 not, 2 error, 3 no Codex here
                                                         # (or Codex never asked to trust this folder)
    python3 Harness/codex-hook-trust.py --trust          # show what would be trusted, write nothing
    python3 Harness/codex-hook-trust.py --trust --yes    # explicitly trust the displayed hooks, as /hooks does

Editing .codex/hooks.json can invalidate trust and prevent a hook from running.
This asks Codex itself, through the app-server methods that
`codex app-server generate-json-schema` documents: hooks/list gives each
hook's key, command, currentHash, trustStatus and enabled; --trust --yes
upserts hooks.state.<key>.trusted_hash = currentHash with config/batchWrite,
after backing up config.toml. Only hooks defined in dev/.codex/hooks.json
count. Codex keys trust by the folder's exact spelling, so start Codex in dev
through codex-start, which uses the canonical path. The whole check keeps to
DEVARNESS_HOOK_TRUST_DEADLINE seconds (45), well inside dev-check's 120 s bound.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
NO_CODEX, ERROR = 3, 2


def codex_command():
    """The codex binary: DEVARNESS_CODEX_BIN when set (tests), else the one on PATH."""
    chosen = os.environ.get("DEVARNESS_CODEX_BIN") or shutil.which("codex")
    if not chosen or not Path(chosen).exists():
        return None
    return [sys.executable, chosen] if chosen.endswith(".py") else [chosen]


class AppServer:
    """A `codex app-server` speaking newline-delimited JSON on stdin and stdout."""

    def __init__(self, command, cwd, deadline):
        self.proc = subprocess.Popen(command + ["app-server"], cwd=cwd, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                     encoding="utf-8", bufsize=1,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.lines = queue.Queue()
        threading.Thread(target=lambda: [self.lines.put(line) for line in self.proc.stdout], daemon=True).start()
        self.next_id = 0
        self.deadline = deadline

    def call(self, method, params):
        self.next_id += 1
        self.proc.stdin.write(json.dumps({"id": self.next_id, "method": method, "params": params}) + "\n")
        self.proc.stdin.flush()
        while time.monotonic() < self.deadline:
            try:
                message = json.loads(self.lines.get(timeout=0.5))
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError("%s: the app-server exited (code %s)" % (method, self.proc.returncode))
                continue
            except ValueError:
                continue
            if message.get("id") == self.next_id:
                if "error" in message:
                    raise RuntimeError("%s failed: %s" % (method, message["error"]))
                return message.get("result") or {}
        raise RuntimeError("%s: no answer before the deadline" % method)

    def notify(self, method):
        self.proc.stdin.write(json.dumps({"method": method}) + "\n")
        self.proc.stdin.flush()

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()


def expected(root):
    """How many hooks dev/.codex/hooks.json defines."""
    data = json.loads((root / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    return sum(len(group.get("hooks", [])) for groups in data.get("hooks", {}).values() for group in groups)


def listed_hooks(server, root):
    """dev's hooks as Codex sees them, and the listing's errors and warnings."""
    source = str(root / ".codex" / "hooks.json").lower()
    hooks, notes = [], []
    for entry in server.call("hooks/list", {"cwds": [str(root)]}).get("data", []):
        hooks += [h for h in entry.get("hooks", []) if str(h.get("sourcePath", "")).lower() == source]
        notes += [str(e) for e in entry.get("errors", []) + entry.get("warnings", [])]
    return hooks, notes


def trust_recorded(config, root):
    """Whether Codex's config holds any trust decision for this folder."""
    try:
        import tomllib
        projects = tomllib.loads(config.read_text(encoding="utf-8")).get("projects", {})
    except (ImportError, OSError, ValueError):
        return True   # cannot tell: keep the strict answer
    want = os.path.normcase(os.path.normpath(str(root)))
    return any(os.path.normcase(os.path.normpath(key)) == want for key in projects)


def state(hook):
    if hook.get("enabled") is False:
        return "disabled"
    return hook.get("trustStatus") or "unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--trust", action="store_true")
    parser.add_argument("--yes", action="store_true", help="with --trust: write the trust records shown")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    command = codex_command()
    if command is None:
        print("codex-hook-trust: Codex is not installed on this device; nothing to check")
        return NO_CODEX
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    if not home.is_dir():
        print("codex-hook-trust: Codex has never run for this user (no %s); nothing to check" % home)
        return NO_CODEX
    deadline = time.monotonic() + float(os.environ.get("DEVARNESS_HOOK_TRUST_DEADLINE", "45"))
    server = None
    try:
        server = AppServer(command, root, deadline)
        server.call("initialize", {"clientInfo": {"name": "codex-start-hook-trust", "version": "1"}})
        server.notify("initialized")
        hooks, notes = listed_hooks(server, root)
        pending = [h for h in hooks if h.get("trustStatus") in ("untrusted", "modified")]
        if args.trust and pending:
            # Codex's trust step exists so a changed command is seen before it runs.
            for hook in pending:
                print("to trust: %s %s matcher=%s\n  command: %s" % (
                    hook.get("eventName"), hook.get("key"), hook.get("matcher"), hook.get("command")))
            if not args.yes:
                print("codex-hook-trust: nothing written; read the commands above, then add --yes to trust them")
                return 1
            config = home / "config.toml"
            shutil.copy2(config, config.with_name("config.toml.bak-hook-trust-" + time.strftime("%Y%m%d-%H%M%S")))
            server.call("config/batchWrite", {"edits": [{
                "keyPath": "hooks.state", "mergeStrategy": "upsert",
                "value": {h["key"]: {"trusted_hash": h["currentHash"]} for h in pending}}]})
            hooks, notes = listed_hooks(server, root)
    except (RuntimeError, OSError, ValueError) as error:
        print("codex-hook-trust: ERROR %s" % error)
        return ERROR
    finally:
        if server is not None:
            server.close()

    want = expected(root)
    for hook in hooks:
        print("  %-9s %-14s %s" % (state(hook), hook.get("eventName"), hook.get("key")))
    bad = [h for h in hooks if state(h) != "trusted"]
    print("codex-hook-trust: %d of %d dev hooks trusted" % (len(hooks) - len(bad), want))
    if not hooks and not trust_recorded(home / "config.toml", root):
        print("codex-hook-trust: Codex has no trust decision for %s on this device; owner: start Codex there "
              "with codex-start, trust the folder, then trust its hooks in /hooks" % root)
        return NO_CODEX
    if len(hooks) < want:
        print("Codex lists %d of %d dev hooks: check that the dev project is trusted and hooks are on in Codex's "
              "config%s" % (len(hooks), want, "".join("\n  " + note for note in notes)))
        return 1
    if bad:
        print("Codex skips a disabled, untrusted or modified hook. Re-enable or trust it in Codex's /hooks, or on "
              "the owner's word run python3 Harness/codex-hook-trust.py --trust, read the commands, then add --yes")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
