"""The start check. Hook JSON by default; --text is a strict CLI gate.

Preflight first, then a fast-forward-only pull of this checkout, then the
verdict. Nothing here commits, sweeps or pushes: agents commit by path and
push their own work. A checkout with no remote gets a note, not a fault.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

HOOKS = Path(__file__).resolve().parent


def _kill_group(pid, sig):
    try:
        if os.name == "nt":
            # Windows has no process groups; /T ends the tree a fetch runs in.
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.killpg(pid, sig)
    except OSError:
        pass


def _launchable(command):
    # Windows cannot execute a shell script (WinError 193): hand it to Git
    # Bash's bash, which the hook and the launchers already run in. The
    # bash.exe in System32 is WSL's and would run the script inside Linux.
    if os.name != "nt" or not command[0].endswith(".sh"):
        return command
    bash = shutil.which("bash")
    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    if not bash or os.path.normcase(os.path.dirname(bash)) == os.path.normcase(system32):
        raise RuntimeError("Git Bash's bash is not on PATH; start dev from Git Bash")
    return [bash, *command]


def run(command, timeout):
    # Own the group so a timeout cannot leave a background fetch running.
    # UTF-8 explicitly: the reports carry em dashes, which a Windows code page
    # such as cp950 cannot decode. Replaced, not strict: one byte in another
    # encoding made the output None and the start START FAILED (Task 8).
    with subprocess.Popen(_launchable(command), stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", errors="replace", start_new_session=True) as process:
        try:
            out, err = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # The old hang was the UNBOUNDED communicate() after SIGKILL below,
            # not this call. os.killpg is guarded too because it raises
            # ProcessLookupError for a group that already exited and
            # PermissionError for a zombie-only group on macOS, and either
            # surfaced as a spurious "START FAILED — [Errno 1]" at exactly timeout s.
            _kill_group(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                _kill_group(process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            raise RuntimeError(
                "{} timed out after {}s. Launchers stop here; on the hook path this is reported, not enforced. "
                "Run `git status`; remove a stale `.git/index.lock` if a SIGKILL left one. "
                "To start without pulling: `touch .claude/hooks/sync.off`".format(
                    Path(command[0]).name, timeout))
        return process.returncode, out, err


def main():
    parser = argparse.ArgumentParser(prog="start-check", description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="readiness and saved pull status only; no fetch, no Git writes")
    parser.add_argument("--text", action="store_true", help="print banner; exit nonzero on failure")
    args = parser.parse_args()
    # Never save hook input, which may contain session metadata.
    if not args.text and not sys.stdin.isatty():
        sys.stdin.read()
    start = time.monotonic()
    if args.text:
        print("START — checking dev before work begins", flush=True)
    lines = []
    context = ""
    allowed = False
    if args.check and args.text:
        os.environ["DEVARNESS_START_ALL"] = "1"  # the healthy banner's pointer: every row, not the count
    try:
        rc, raw, err = run([str(HOOKS / "preflight.sh")], 10)
        if rc:
            raise RuntimeError("preflight exited {}".format(rc))
        if not raw.strip():
            # A bare JSON decode error hid a refused here-document.
            detail = err.strip().splitlines()[-1][:300] if err.strip() else "no stderr"
            raise RuntimeError("preflight produced no output ({})".format(detail))
        report = json.loads(raw)
        banner = report.get("systemMessage")
        context = report.get("additionalContext", "")
        if not isinstance(context, str):
            context = ""
            raise RuntimeError("preflight returned invalid additionalContext")
        if not isinstance(banner, str) or not banner.startswith("START ready\n"):
            raise RuntimeError("preflight did not produce a valid readiness banner")
        lines.extend(banner.splitlines()[1:])
        if args.text:
            print("\n".join(lines), flush=True)
        # claude-start / codex-start run the full gate in the foreground and then exec the
        # client, whose own SessionStart hook lands here. The launcher exports the
        # time its gate ended READY — and only then, so a DEGRADED launch (offline,
        # busy) still gets the hook's pull as a second chance; within five minutes,
        # report status instead of pulling again.
        gate_done = os.environ.get("DEVARNESS_START_GATE_DONE", "")
        if not args.check and gate_done.isdigit() and 0 <= time.time() - int(gate_done) < 300:
            args.check = True
            launcher_note = "pull: the launcher gate ended READY %ds ago; status only, not pulled again\n" % int(time.time() - int(gate_done))
        else:
            launcher_note = ""

        if args.check:
            rc, out, err = run([str(HOOKS / "sync.sh"), "--status"], 5)
            if rc:
                raise RuntimeError("saved pull status could not be read")
            sync = launcher_note + "pull: status only (no pull requested)\n" + out.strip()
        else:
            if args.text:
                print("PULL — fast-forwarding this checkout from origin", flush=True)
            rc, out, err = run([str(HOOKS / "sync.sh"), "--pull"], 100)
            sync = "\n".join(s.strip() for s in (out, err) if s.strip())
            if rc not in (0, 1, 4):
                lines.append(sync)
                if args.text and sync:
                    print(sync, flush=True)
                raise RuntimeError("pull {} (exit {}); inspect the report above before retrying".format(
                    {2: "REFUSED"}.get(rc, "FAILED"), rc))
            if rc == 1:
                sync += "\npull: OFFLINE or NOT FAST-FORWARDED — local work only; not up to date"
        lines.append(sync)
        if args.text:
            print(sync, flush=True)
        # A missing remote is a note: dev starts life with none. Everything that
        # leaves this checkout behind origin, or stops the pull, is DEGRADED.
        states = sync.lower()
        degraded = ("Degraded:" in banner or rc in (1, 4)
                    or any(word in states for word in ("refused", "paused", "offline", "diverged", "not pulled")))
        result = "START COMPLETE — {} ({:.2f}s)".format(
            "DEGRADED; read the notes above" if degraded else "READY", time.monotonic() - start)
        allowed = True
    except (OSError, ValueError, AttributeError, RuntimeError) as error:
        result = "START FAILED — {}".format(error)
    lines.append(result)
    context += (" The start check must finish before work. Read CLAUDE.md and the applicable "
                "project instructions. Configured Claude plugins are not proof that this "
                "Codex session exposes their tools. Never silently resolve a diverged branch "
                "or a merge conflict. Readiness checks do not mean all Markdown or source files were read. ")
    context += result
    if args.text:
        print(result, flush=True)
        return 0 if allowed else 1
    # `continue` / `stopReason`: Claude Code IGNORES both from SessionStart
    # (hooks reference; confirmed in the 2.1.265 binary), so for Claude the hook
    # path is ADVISORY — systemMessage and additionalContext are honoured and
    # both carry START FAILED loudly; the CLI launchers enforce it. Codex's
    # session-start output schema accepts the same two fields and may honour
    # them (unverified), so they are emitted for that path and the docs say
    # exactly which client does what. Dropping them was briefly tried and
    # would have regressed Codex if it does honour them.
    output = {"continue": allowed, "systemMessage": "\n".join(lines),
              "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    if not allowed:
        output["stopReason"] = result
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
