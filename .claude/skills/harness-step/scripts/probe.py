#!/usr/bin/env python3
"""Run one dev task under one harness, headless, and keep what it did.

The Probe stage of harness-step (after Harness2's Propose-Probe-Compose). Each run
gets its own detached worktree at a commit, optionally with a candidate patch applied,
so the reference and every candidate face the same task, model and settings. The run's
trajectory (stream-json), its deliverable (the worktree diff) and a summary are kept;
the worktree is removed afterwards.

  probe.py run --task task.md --label base --out DIR [--patch cand.diff] [--ref HEAD]
  probe.py summary DIR          -> one row per run: turns, tools, errors, tokens, cost
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/harness-step/scripts -> dev root
# Automatic approval patterns; these do not remove other tools or provide a sandbox.
DEFAULT_TOOLS = "Read,Grep,Glob,Edit,Write,Skill,Bash(md-format:*),Bash(git status:*),Bash(git diff:*)"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# Git-ignored state a dev session reads besides the clones Library/repos.txt names.
RUNTIME_DIRS = ("Library/.runtime",)
# Copied, never linked: a library refresh in the tree must write its own index, not main's.
SEEDED_FILES = (".claude/hooks/library/index.json",)
# The start banner: "START COMPLETE — DEGRADED; ..." and rows "  name<pad>state<pad>note".
START_LINE = re.compile(r"^START (?:COMPLETE|FAILED)[^;\n]*", re.M)
BANNER_ROW = re.compile(r"^  (\S.{0,15}?) {2,}(\S+(?: \S+)?)(?: {2,}|$)", re.M)
# Why a start is degraded: "Degraded: <reason>" lines, which carry no capability row.
DEGRADED_LINE = re.compile(r"^Degraded: (.+)$", re.M)


def git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True,
                          encoding="utf-8", creationflags=NO_WINDOW)
    if done.returncode:
        raise SystemExit("git {} failed: {}".format(" ".join(args), done.stderr.strip()))
    return done.stdout


def summarize(trajectory: Path) -> dict:
    """Count what the run did from its stream-json events; the result event carries usage."""
    tools, errors, denied, result = Counter(), 0, 0, {}
    start, capabilities, degraded, prompt_hooks, prompt_hook_chars = None, {}, [], 0, 0
    for line in trajectory.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # a stray non-JSON line (a hook's banner) is not an event
        if event.get("type") == "result":
            result = event
        if event.get("subtype") == "permission_denied":
            denied += 1
        if event.get("subtype") == "hook_response" and event.get("hook_event") == "SessionStart":
            banner = _banner_text(event.get("output") or "")
            found = START_LINE.search(banner)
            start = found.group(0).strip() if found else start
            capabilities.update(BANNER_ROW.findall(banner))
            degraded += DEGRADED_LINE.findall(banner)
        if event.get("subtype") == "hook_response" and event.get("hook_event") == "UserPromptSubmit":
            prompt_hooks += 1
            prompt_hook_chars += len(event.get("output") or "")
        message = event.get("message")
        if not isinstance(message, dict):
            continue  # system events carry their message as text
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                tools[block.get("name", "?")] += 1
            if block.get("type") == "tool_result" and block.get("is_error"):
                errors += 1
    usage = result.get("usage") or {}
    tokens = sum(usage.get(k, 0) or 0 for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return {
        "delivered": result.get("subtype") == "success" and not result.get("is_error"),
        "turns": result.get("num_turns"),
        "tool_calls": sum(tools.values()),
        "tools": dict(tools.most_common()),
        "tool_errors": errors,
        "denied": denied,
        "tokens": tokens,
        "cost_usd": result.get("total_cost_usd"),
        "seconds": round((result.get("duration_ms") or 0) / 1000),
        "final_text": (result.get("result") or "")[:2000],
        "start": start,
        "capabilities": capabilities,
        "degraded": degraded,
        "prompt_hooks": prompt_hooks,
        "prompt_hook_chars": prompt_hook_chars,
    }


def _banner_text(output: str) -> str:
    """A SessionStart hook prints JSON whose systemMessage is the banner, or plain text."""
    try:
        return json.loads(output).get("systemMessage") or ""
    except (json.JSONDecodeError, AttributeError):
        return output  # plain text, or JSON that is not an object


def link_clones(tree: Path) -> list:
    """Link each git-ignored clone and runtime present in the main checkout into the probe tree,
    and copy in each seeded file.

    A worktree checks out tracked files only, so without these the probe runs a harness
    with no library picks, Vercel find or TieItUp. Junctions on Windows need no admin
    right and no subprocess; the clones are shared, never copied.
    """
    main = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")).parent
    repos = main / "Library" / "repos.txt"
    listed = [row.split("\t")[0] for row in repos.read_text(encoding="utf-8").splitlines()
              if row.strip() and not row.startswith("#")] if repos.is_file() else []
    linked = []
    for relative in listed + list(RUNTIME_DIRS):
        source, target = main / relative, tree / relative
        if not source.is_dir() or os.path.lexists(target):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(str(source), str(target))
        else:
            os.symlink(source, target, target_is_directory=True)
        linked.append(relative)
    for relative in SEEDED_FILES:
        source, target = main / relative, tree / relative
        if not source.is_file() or os.path.lexists(target):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        linked.append(relative)
    return linked


def unlink_clones(tree: Path, linked: list) -> None:
    """Remove only what link_clones made, so removing the worktree cannot reach into the clones."""
    for relative in linked:
        target = tree / relative
        if not os.path.lexists(target):
            continue  # already removed: run unlinks before the diff and again on the way out
        if target.is_symlink() or target.is_file():
            target.unlink()  # a symlink, or a seeded copy
        else:
            os.rmdir(target)  # a junction: removes the link, never the target's contents


def run(args: argparse.Namespace) -> int:
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("claude is not on PATH; a probe needs the Claude Code CLI")
    out = Path(args.out).resolve()
    if any((out / (args.label + ext)).exists() for ext in (".jsonl", ".diff", ".summary.json")):
        raise SystemExit("{} already has evidence for {}; use a new label".format(out, args.label))
    out.mkdir(parents=True, exist_ok=True)
    task = Path(args.task).read_text(encoding="utf-8")
    commit = git("rev-parse", "--verify", args.ref + "^{commit}").strip()  # every run names the same commit
    tree = ROOT / ".claude" / "worktrees" / "probe-{}-{}".format(args.label, int(time.time()))
    git("worktree", "add", "--detach", "--no-checkout", str(tree), commit)
    linked = []
    try:
        # Clones first, so git makes tracked skill links into them as folder links on Windows.
        linked = link_clones(tree)
        git("reset", "-q", "--hard", cwd=tree)
        if args.patch:
            git("apply", "--whitespace=nowarn", str(Path(args.patch).resolve()), cwd=tree)
            git("add", "-A", cwd=tree)  # the candidate becomes the baseline the diff is taken against
            git("-c", "user.name=probe", "-c", "user.email=probe@localhost",
                "commit", "-q", "--no-verify", "-m", "candidate " + args.label, cwd=tree)
        # The launcher-gate variable makes the start check report status instead of pulling.
        env = dict(os.environ, DEVARNESS_START_GATE_DONE=str(int(time.time())))
        # Without --include-hook-events the stream omits UserPromptSubmit output (CLI 2.1.292).
        cmd = [claude, "-p", task, "--output-format", "stream-json", "--verbose", "--include-hook-events",
               "--permission-mode", "acceptEdits", "--allowedTools", args.tools,
               "--max-budget-usd", str(args.max_usd), "--no-session-persistence"]
        if args.model:
            cmd += ["--model", args.model]
        trajectory = out / (args.label + ".jsonl")
        with open(trajectory, "w", encoding="utf-8", newline="\n") as fh:
            try:
                done = subprocess.run(cmd, cwd=tree, env=env, stdout=fh, stderr=subprocess.PIPE,
                                      text=True, encoding="utf-8", timeout=args.timeout,
                                      creationflags=NO_WINDOW)
                exit_code, stderr = done.returncode, done.stderr or ""
            except subprocess.TimeoutExpired as late:  # a timed-out run is evidence too
                exit_code, stderr = "timeout", str(late)
        # Off Windows the links are symlinks, which ignore patterns ending in "/" miss.
        unlink_clones(tree, linked)
        git("add", "-A", "-N", cwd=tree)  # intent-to-add, so new files show in the diff
        _write_lf(out / (args.label + ".diff"), git("diff", cwd=tree))
        summary = dict(summarize(trajectory), label=args.label, ref=commit, ref_arg=args.ref,
                       patch=args.patch, model=args.model, links=linked, exit=exit_code,
                       stderr=stderr.strip()[-500:])
        summary["delivered"] = summary["delivered"] and exit_code == 0  # CLI completion, not acceptance
        _write_lf(out / (args.label + ".summary.json"), json.dumps(summary, indent=2) + "\n")
        print(json.dumps({k: summary[k] for k in ("label", "delivered", "turns", "tool_calls",
                                                  "tool_errors", "denied", "tokens", "cost_usd")}))
        return 0 if summary["delivered"] else 1
    finally:
        if not args.keep:
            unlink_clones(tree, linked)
            git("worktree", "remove", "--force", str(tree))


def _write_lf(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def table(args: argparse.Namespace) -> int:
    rows = sorted(Path(args.out).glob("*.summary.json"))
    if not rows:
        raise SystemExit("no *.summary.json under {}".format(args.out))
    print("| run | delivered | turns | tool calls | tool errors | denied | tokens | cost USD | top tools |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for path in rows:
        s = json.loads(path.read_text(encoding="utf-8"))
        top = ", ".join("{} {}".format(k, v) for k, v in list(s["tools"].items())[:5])
        print("| {label} | {delivered} | {turns} | {tool_calls} | {tool_errors} | {denied} | {tokens} | {cost_usd} | {top} |"
              .format(top=top, **s))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the task once under one harness")
    r.add_argument("--task", required=True, help="Markdown file whose text is the prompt")
    r.add_argument("--label", required=True, help="run name: base, base2, inv, dom, composed")
    r.add_argument("--out", required=True, help="evidence folder for the step")
    r.add_argument("--patch", help="candidate harness as a git diff against --ref")
    r.add_argument("--ref", default="HEAD", help="commit the harness is taken from")
    r.add_argument("--tools", default=DEFAULT_TOOLS, help="automatic approval patterns, comma separated; not a sandbox")
    r.add_argument("--max-usd", type=float, default=3.0, help="per-run spend cap passed to claude")
    r.add_argument("--timeout", type=int, default=1200, help="seconds before the run is killed")
    r.add_argument("--model", help="model alias; default is the session default")
    r.add_argument("--keep", action="store_true", help="leave the worktree for inspection")
    s = sub.add_parser("summary", help="tabulate every run in an evidence folder")
    s.add_argument("out")
    args = parser.parse_args()
    return run(args) if args.cmd == "run" else table(args)


if __name__ == "__main__":
    sys.exit(main())
