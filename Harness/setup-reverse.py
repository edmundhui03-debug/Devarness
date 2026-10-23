#!/usr/bin/env python3
"""setup-reverse.py — place the REA and reverse-skill runtimes under Harness/.runtime, locally and verified.

  python3 Harness/setup-reverse.py --from DIR     verify every archive in DIR against
                                                  Harness/setup/reverse-downloads.json, then unpack
                                                  into Harness/.runtime/<tool>/ and npm ci the REA runtime
  python3 Harness/setup-reverse.py --check        report per tool ok/missing, change nothing,
                                                  exit 1 with the install command if any is missing
  python3 Harness/setup-reverse.py --check --doctor   also run, through dev's own launchers, REA's
                                                  scoped doctor (rea doctor --provider ghidra --json)
                                                  and reverse jadx/apktool --version; exit 1 naming
                                                  whatever is not ready (6 s on the build PC)

DIR may be flat (every archive in DIR) or one folder per tool (DIR/jdk/..., DIR/node/...).
Every archive's SHA-256 is checked against the manifest BEFORE it is unpacked; a mismatch
refuses the whole install and nothing is written. Each tool unpacks into a fresh folder under
Harness/.runtime and is skipped on a second run once its stamp matches. REA installs from the
tracked lock with the local Node, its cache kept inside Harness/.runtime/npm-cache, scripts off.
The dev root is derived from this file's location; no absolute machine path is written. Standard
library only. Owner request 2026-10-08; dev-work/reverse/RECIPE.md sections 4 and 5.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

LIBRARY = Path(__file__).resolve().parent
RUNTIME = LIBRARY / ".runtime"
MANIFEST = LIBRARY / "setup" / "reverse-downloads.json"
REA_SETUP = LIBRARY / "setup" / "rea"
REA_INTEGRITY = "sha512-BOig7QyPtOJLZtCa7MIVyecGdsI5C8kX0HHjp9Fo5LkotSqD3cRV91KCp0pakLqLuyF1BFl4RSyV/9F/Wk6OBQ=="

# Entry point each tool must present once it is in place; '*/' allows the one versioned
# top-level folder that the Node and JDK archives carry.
ENTRY = {
    "jdk": ["bin/java.exe", "*/bin/java.exe"],
    "node": ["node.exe", "*/node.exe"],
    "ghidra": ["support/analyzeHeadless.bat", "*/support/analyzeHeadless.bat"],
    "jadx": ["bin/jadx.bat", "*/bin/jadx.bat"],
    "apktool": ["apktool.jar"],
    "rea": ["node_modules/rea-agents/scripts/rea.mjs"],
}
ARCHIVE_TOOLS = ["jdk", "node", "ghidra", "jadx", "apktool"]
REQUIRED = ARCHIVE_TOOLS + ["rea"]
APKTOOL_BAT = "@echo off\r\nsetlocal\r\njava -jar \"%~dp0apktool.jar\" %*\r\n"
INSTALL = ("python Harness/setup-reverse.py --from <folder holding the archives in "
           "Harness/setup/reverse-downloads.json, such as the USB's reverse folder>")
# What --doctor runs, through the launchers an agent uses: name, launcher, arguments, seconds.
DOCTOR = (("rea", "rea", ["doctor", "--provider", "ghidra", "--json"], 300),
          ("jadx", "reverse", ["jadx", "--version"], 120),
          ("apktool", "reverse", ["apktool", "--version"], 120))


def load_manifest(path=MANIFEST):
    return json.loads(Path(path).read_text(encoding="utf-8"))["tools"]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_archive(src_dir, tool, filename):
    """Locate an archive in a flat DIR, a per-tool subfolder, or anywhere below DIR."""
    src_dir = Path(src_dir)
    for cand in (src_dir / filename, src_dir / tool / filename):
        if cand.is_file():
            return cand
    found = sorted(src_dir.rglob(filename))
    return found[0] if found else None


def entry_point(tool, runtime_root=RUNTIME):
    base = Path(runtime_root) / tool
    for pat in ENTRY[tool]:
        hits = sorted(base.glob(pat))
        if hits:
            return hits[0]
    return None


def verify_archives(src_dir, manifest):
    """Return (resolved, problems). Resolved maps tool -> (path, sha). Computes hashes; unpacks nothing."""
    resolved, problems = {}, []
    for tool in ARCHIVE_TOOLS:
        meta = manifest[tool]
        path = find_archive(src_dir, tool, meta["file"])
        if path is None:
            problems.append("%s: %s not found under %s" % (tool, meta["file"], src_dir))
            continue
        actual = sha256_of(path)
        if actual != meta["sha256"]:
            problems.append("%s: SHA-256 mismatch for %s (want %s, got %s)"
                            % (tool, path, meta["sha256"], actual))
            continue
        resolved[tool] = (path, actual)
    return resolved, problems


def _stamp(tool, runtime_root):
    return Path(runtime_root) / tool / ".verified.json"


def _stamped(tool, runtime_root, sha):
    try:
        data = json.loads(_stamp(tool, runtime_root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("sha256") == sha and entry_point(tool, runtime_root) is not None


def unpack_tool(tool, archive, sha, runtime_root):
    """Unpack one verified archive into a fresh Harness/.runtime/<tool>/ folder. Idempotent."""
    if _stamped(tool, runtime_root, sha):
        return "skip"
    dest = Path(runtime_root) / tool
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if tool == "apktool":
        shutil.copy2(archive, dest / "apktool.jar")
        (dest / "apktool.bat").write_text(APKTOOL_BAT, encoding="ascii")
    else:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    if entry_point(tool, runtime_root) is None:
        raise SystemExit("%s: unpacked but its entry point is missing under %s" % (tool, dest))
    _stamp(tool, runtime_root).write_text(json.dumps({"sha256": sha}) + "\n", encoding="ascii")
    return "ok"


def _node_exe(runtime_root):
    return entry_point("node", runtime_root)


def _lock_integrity():
    try:
        lock = json.loads((REA_SETUP / "package-lock.json").read_text(encoding="utf-8"))
        return lock["packages"]["node_modules/rea-agents"]["integrity"]
    except (OSError, ValueError, KeyError):
        return None


def install_rea(runtime_root):
    """npm ci the REA runtime from the tracked lock, with the local Node, cache inside the runtime."""
    rea_dir = Path(runtime_root) / "rea"
    if entry_point("rea", runtime_root) is not None and _lock_integrity() == REA_INTEGRITY:
        stamp = rea_dir / ".installed.json"
        if stamp.is_file():
            try:
                if json.loads(stamp.read_text(encoding="utf-8")).get("integrity") == REA_INTEGRITY:
                    return "skip"
            except ValueError:
                pass
    node = _node_exe(runtime_root)
    if node is None:
        raise SystemExit("rea: Node is not in place; unpack it before installing REA")
    integrity = _lock_integrity()
    if integrity != REA_INTEGRITY:
        raise SystemExit("rea: package-lock.json integrity is %r, expected the pinned 4.1.0 sha512" % integrity)
    npm_cli = node.parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    rea_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REA_SETUP / "package.json", rea_dir / "package.json")
    shutil.copy2(REA_SETUP / "package-lock.json", rea_dir / "package-lock.json")
    env = dict(os.environ)
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
    env["npm_config_cache"] = str(Path(runtime_root) / "npm-cache")
    env["npm_config_update_notifier"] = "false"
    kw = {}
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # hide any console; keep inherited stdio intact
        kw["startupinfo"] = si
    subprocess.run([str(node), str(npm_cli), "ci", "--omit=dev", "--ignore-scripts",
                    "--no-audit", "--no-fund"], cwd=str(rea_dir), env=env, check=True, **kw)
    if entry_point("rea", runtime_root) is None:
        raise SystemExit("rea: npm ci finished but scripts/rea.mjs is missing")
    (rea_dir / ".installed.json").write_text(json.dumps({"integrity": REA_INTEGRITY}) + "\n", encoding="ascii")
    return "ok"


def check(runtime_root=RUNTIME):
    """Report per tool ok/missing. Returns (lines, exit_code); exit 1 if any required tool is missing."""
    lines, missing = [], False
    for tool in REQUIRED:
        ep = entry_point(tool, runtime_root)
        lines.append("  %-8s %s" % (tool, ("ok  " + str(ep)) if ep else "MISSING"))
        if ep is None:
            missing = True
    return lines, (1 if missing else 0)


def rea_verdict(stdout):
    """'' when REA's scoped doctor is healthy, else what failed: its unhealthy scope checks."""
    try:
        report = json.loads(stdout)
    except ValueError:
        return "no JSON from rea doctor"
    failed = [c.get("name", "?") for c in report.get("scope_checks", []) if not c.get("ok")]
    if report.get("healthy") is True and not failed:
        return ""
    return "unhealthy: " + (", ".join(failed) or "healthy is not true")


def doctor(runtime_root=RUNTIME):
    """Run each DOCTOR command against runtime_root. Returns (lines, problems)."""
    env = dict(os.environ, DEVARNESS_REVERSE_RUNTIME=str(runtime_root))
    lines, problems = [], []
    for name, launcher, args, seconds in DOCTOR:
        try:
            done = subprocess.run([sys.executable, str(LIBRARY / "bin" / launcher), *args], env=env,
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=seconds,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out = done.stdout.strip()
            if name == "rea":
                why = rea_verdict(out) or ("exit %d" % done.returncode if done.returncode else "")
                shown = "doctor --provider ghidra healthy"
            else:
                shown = out.splitlines()[-1] if out else ""
                why = "exit %d" % done.returncode if done.returncode else ("" if shown else "no version printed")
        except subprocess.TimeoutExpired:
            why = "timed out after %d s" % seconds
        lines.append("  %-8s %s" % (name, ("ok  " + shown) if not why else "NOT READY  " + why))
        if why:
            problems.append("%s (%s)" % (name, why))
    return lines, problems


def install(src_dir, runtime_root=RUNTIME, manifest=None):
    manifest = manifest or load_manifest()
    resolved, problems = verify_archives(src_dir, manifest)
    if problems:
        for p in problems:
            print("  REFUSED: " + p, file=sys.stderr)
        raise SystemExit("setup-reverse: archive verification failed; nothing was unpacked")
    Path(runtime_root).mkdir(parents=True, exist_ok=True)
    results = {}
    for tool in ARCHIVE_TOOLS:
        path, sha = resolved[tool]
        results[tool] = unpack_tool(tool, path, sha, runtime_root)
        print("  %-8s %s" % (tool, results[tool]))
    results["rea"] = install_rea(runtime_root)
    print("  %-8s %s" % ("rea", results["rea"]))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install the REA and reverse-skill runtimes under Harness/.runtime.")
    ap.add_argument("--from", dest="src", help="folder holding the verified archives (flat or per tool)")
    ap.add_argument("--check", action="store_true", help="report per tool ok/missing; change nothing")
    ap.add_argument("--doctor", action="store_true", help="with --check: also run REA's doctor and the tool versions")
    ap.add_argument("--runtime-root", default=str(RUNTIME), help="override the runtime root (tests, relocation)")
    ap.add_argument("--manifest", default=str(MANIFEST), help="override the download manifest (tests)")
    args = ap.parse_args(argv)
    runtime_root = Path(args.runtime_root)
    if args.doctor and not args.check:
        ap.error("--doctor goes with --check")

    if args.check:
        lines, code = check(runtime_root)
        print("reverse runtime:")
        for line in lines:
            print(line)
        if code:
            print("install: " + INSTALL)
            return code
        if not args.doctor:
            return 0
        lines, problems = doctor(runtime_root)
        print("reverse doctor:")
        for line in lines:
            print(line)
        print("reverse tools: " + ("NOT READY: " + "; ".join(problems) if problems else "READY"))
        return 1 if problems else 0

    if not args.src:
        ap.error("--from DIR is required unless --check is given")
    manifest = load_manifest(args.manifest)
    install(args.src, runtime_root, manifest)
    lines, code = check(runtime_root)
    print("reverse runtime:")
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
