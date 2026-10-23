#!/usr/bin/env python3
"""Pinned, local learn-claude-code lab. No installation into either agent host."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

LIBRARY = Path(__file__).resolve().parent
REPO = "learn-claude-code"
URL = "https://github.com/shareAI-lab/learn-claude-code.git"
PIN = "0dcafa2ae053a1ddd6a72f265431104b08a5aa13"
PYTHON_VERSION = "3.11.16"
# Complete uv resolution for Python 3.11, refreshed intentionally with the source pin.
DEPENDENCIES = """annotated-types==0.8.0
anthropic==1.4.0
anyio==4.15.1
docstring-parser==0.18.0
h11==0.16.0
httpcore2==2.12.0
httpx2==2.12.0
idna==3.19
iniconfig==2.3.0
jiter==0.16.0
packaging==26.3
pluggy==1.6.0
pydantic==2.13.5
pydantic-core==2.46.5
pygments==2.21.0
pytest==9.1.1
python-dotenv==1.2.3
pyyaml==6.0.3
sniffio==1.3.1
truststore==0.10.4
typing-extensions==4.16.0
typing-inspection==0.4.4
"""
GUARD = '''import sys
def offline_audit(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto"}:
        raise RuntimeError("network access disabled in the dev lesson verification")
sys.addaudithook(offline_audit)
'''


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True, **kwargs)


def manifest_pin(library=LIBRARY):
    rows = [line.split("\t") for line in (library / "repos.txt").read_text().splitlines()
            if line and not line.startswith("#")]
    matches = [row for row in rows if row[0] == "Harness/" + REPO]
    if len(matches) != 1 or matches[0][1:] != [URL, PIN]:
        raise RuntimeError("repos.txt must contain the reviewed learn-claude-code URL and pin")
    return PIN


def locations(library=LIBRARY):
    if os.name != "posix":
        raise RuntimeError("the full lesson lab requires POSIX (upstream imports fcntl); use WSL on Windows")
    commit = manifest_pin(library)
    source = library / REPO
    runtime = library / ".runtime" / REPO / commit
    return source, runtime, runtime / "source", runtime / ".venv" / "bin" / "python"


def verify_clone(source):
    head = run(["git", "-C", source, "rev-parse", "HEAD"], capture_output=True).stdout.strip()
    dirty = run(["git", "-C", source, "status", "--porcelain", "--untracked-files=all"],
                capture_output=True).stdout.strip()
    origin = run(["git", "-C", source, "remote", "get-url", "origin"],
                 capture_output=True).stdout.strip()
    if head != PIN or dirty or origin.rstrip("/").removesuffix(".git") != URL.removesuffix(".git"):
        raise RuntimeError("source clone is missing, dirty, has the wrong origin, or differs from pin")


def verify_copy(source, copy):
    entries = run(["git", "-C", source, "ls-tree", "-rz", PIN], capture_output=True).stdout
    count = 0
    for entry in entries.split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        mode, kind, expected = metadata.split()
        path = copy / name
        if kind != "blob" or mode not in {"100644", "100755"} or path.is_symlink():
            raise RuntimeError("unsupported source entry: " + name)
        data = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if expected != actual:
            raise RuntimeError("runtime source differs from the pin: " + name)
        count += 1
    return count


def extract_archive(archive, destination):
    with tarfile.open(archive) as handle:
        for member in handle.getmembers():
            # A tar name is a POSIX path; Windows also reads a drive or a
            # backslash in it, and to its Path "/absolute" is not absolute.
            shapes = [PurePosixPath(member.name)] + ([PureWindowsPath(member.name)] if os.name == "nt" else [])
            if (any(shape.anchor or ".." in shape.parts for shape in shapes) or
                    not (member.isfile() or member.isdir())):
                raise RuntimeError("unsupported or unsafe archive entry")
        handle.extractall(destination)


def dependency_versions(python):
    code = "import platform; assert platform.python_version() == " + repr(PYTHON_VERSION) + ", 'Python version differs from the tested pin'; "
    code += "import anthropic, dotenv, yaml, pytest; import importlib.metadata as m; "
    code += "import json; print(json.dumps({d.metadata['Name'].lower().replace('_','-'): d.version for d in m.distributions()}))"
    result = run([python, "-B", "-c", code], capture_output=True,
                 env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return json.loads(result.stdout)


def check(library=LIBRARY):
    source, runtime, copy, python = locations(library)
    verify_clone(source)
    count = verify_copy(source, copy)
    packages = dependency_versions(python)
    expected = dict(line.split("==") for line in DEPENDENCIES.splitlines())
    if any(packages.get(name) != version for name, version in expected.items()):
        raise RuntimeError("runtime dependencies differ from the reviewed pins; run --install")
    return {"status": "prepared", "commit": PIN, "source_pristine": True,
            "runtime_source_files_verified": count, "dependencies": packages,
            "model_api_calls_verified": False, "live_credentials_required": True,
            "runtime": str(runtime.relative_to(library.parent))}


def install(library=LIBRARY):
    source, runtime, copy, python = locations(library)
    verify_clone(source)
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required; install it through the dev bootstrap first")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    lock = runtime.parent / (PIN + ".install.lock")
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise RuntimeError("installation lock exists; inspect it before retrying") from error
    try:
        runtime.mkdir(exist_ok=True)
        if not copy.exists():
            archive = runtime / "source.tar"
            run(["git", "-C", source, "archive", "--format=tar", PIN, "-o", archive])
            copy.mkdir()
            extract_archive(archive, copy)
        verify_copy(source, copy)
        lockfile = runtime / "requirements.lock"
        lockfile.write_text(DEPENDENCIES)
        if not python.exists():
            run([uv, "venv", "--python", PYTHON_VERSION, runtime / ".venv"])
        run([uv, "pip", "sync", "--python", python, lockfile])
        result = check(library)
        (runtime / "installation.json").write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        lock.rmdir()


def offline_environment(guard, python):
    # Credential values and arbitrary Python/pytest startup configuration are not inherited.
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP")
           if key in os.environ}
    env["PATH"] = str(python.parent) + os.pathsep + env.get("PATH", "")
    env.update({"PYTHONPATH": str(guard), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "0",
                "PYTHON_DOTENV_DISABLED": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "ANTHROPIC_API_KEY": "offline-dummy", "MODEL_ID": "offline-model",
                "ANTHROPIC_BASE_URL": "http://127.0.0.1:9",
                "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign",
                "GIT_CONFIG_VALUE_0": "false"})
    return env


def verify(library=LIBRARY):
    result = check(library)
    _, runtime, copy, python = locations(library)
    # Upstream compaction tests include paths in exact character budgets. Keep
    # their scratch paths short; a deeply nested dev runtime changes that fixture.
    with tempfile.TemporaryDirectory(prefix="lcc-", dir="/tmp") as tmp:
        temporary = Path(tmp)
        guard = temporary / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(GUARD)
        env = offline_environment(guard, python)
        blocked = run([python, "-c", "import socket\ntry: socket.create_connection(('127.0.0.1',9))\nexcept RuntimeError: print('blocked')\nelse: raise SystemExit(1)"],
                      env=env, capture_output=True)
        if blocked.stdout.strip() != "blocked":
            raise RuntimeError("offline network guard did not run")
        completed = run([python, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                         "--basetemp", temporary / "pytest", copy / "tests"],
                        cwd=temporary, env=env, capture_output=True, timeout=180)
        (runtime / "pytest.log").write_text(completed.stdout + completed.stderr)
        demo = temporary / "code.py"
        shutil.copy2(copy / "s16_workflow_runtime" / "code.py", demo)
        first = run([python, "-B", demo, "demo"], cwd=temporary, env=env,
                    capture_output=True, timeout=30)
        resumed = run([python, "-B", demo, "resume"], cwd=temporary, env=env,
                      capture_output=True, timeout=30)
        if "status=completed" not in first.stdout or "status=completed  agents=0  tokens=0" not in resumed.stdout:
            raise RuntimeError("workflow demo or resume did not prove completion/cache reuse")
        cli = run([python, "-B", copy / "s01_agent_loop" / "code.py"], cwd=temporary,
                  env=env, input="q\n", capture_output=True, timeout=15)
        if "s01: Agent Loop" not in cli.stdout:
            raise RuntimeError("lesson CLI did not start")
        result.update({"pytest": completed.stdout.strip().splitlines()[-1],
                       "offline_socket_guard": "passed", "s01_cli_quit": "passed",
                       "s16_demo": "completed with fixed mock responses",
                       "s16_resume": "completed with agents=0 tokens=0 (mock cache)",
                       "model_api_calls_made": 0})
    verify_clone(locations(library)[0])
    (runtime / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def launch(lesson, args, library=LIBRARY):
    check(library)
    _, _, copy, python = locations(library)
    if not re.fullmatch(r"s(?:0[1-9]|1[0-7])", lesson):
        raise RuntimeError("choose a current lesson s01 through s17")
    matches = list(copy.glob(lesson + "_*/code.py"))
    if len(matches) != 1:
        raise RuntimeError("lesson is missing or ambiguous")
    if args[:1] in (["demo"], ["resume"]) and lesson == "s16":
        return run([python, "-B", matches[0], *args], cwd=copy).returncode
    if args:
        raise RuntimeError("live lessons are interactive; only s16 accepts demo or resume here")
    if not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("MODEL_ID"):
        raise RuntimeError("live lessons require exported ANTHROPIC_API_KEY and MODEL_ID; no credential file is created")
    env = {**os.environ, "PYTHON_DOTENV_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    print("Starting teaching code in the isolated runtime copy. Shell access is not sandboxed.", flush=True)
    return run([python, "-B", matches[0]], cwd=copy, env=env).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(prog="learn-claude", description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install", action="store_true", help="archive pin and install isolated Python dependencies")
    group.add_argument("--check", action="store_true", help="read-only source, runtime and dependency check")
    group.add_argument("--verify", action="store_true", help="offline upstream tests, CLI quit and mock workflow replay")
    parser.add_argument("lesson", nargs="?", help="current lesson s01–s17; live execution needs explicit credentials")
    parser.add_argument("lesson_args", nargs=argparse.REMAINDER, help="s16 demo or resume are credential-free")
    args = parser.parse_args(argv)
    if args.lesson and (args.install or args.check or args.verify):
        parser.error("choose either an operation or a lesson")
    try:
        if args.lesson:
            return launch(args.lesson, args.lesson_args)
        if not (args.install or args.check or args.verify):
            parser.print_help()
            return 0
        if (args.install or args.check) and os.name != "posix":
            # Nothing to install here, as the preflight and new-device say; a failure
            # would leave update-tools calling the tool stuck on every Windows start.
            print(json.dumps({"applicable": False, "reason": "the lesson lab needs POSIX; use WSL on Windows"}))
            return 0
        result = install() if args.install else verify() if args.verify else check()
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # Child commands run with synthetic credentials during verification; only bounded output.
        if isinstance(error, subprocess.CalledProcessError) and args.verify:
            print((error.stdout or "")[-6000:], file=sys.stderr)
            print((error.stderr or "")[-2000:], file=sys.stderr)
        print("learn-claude-code: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
