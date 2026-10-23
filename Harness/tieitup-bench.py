#!/usr/bin/env python3
"""TieItUp's benchmark: Ponytail's agentic harness with TieItUp in the ponytail2 slot.

  python -B Harness/tieitup-bench.py selftest                 no model call
  python -B Harness/tieitup-bench.py probe                    one "Reply with: ok" session per arm
  python -B Harness/tieitup-bench.py run --budget USD [--runs N]
  python -B Harness/tieitup-bench.py auto                     the pilot after a harness move, within its cap

probe, run and auto start paid sessions. The harness is imported by path and never
edited or written into; raw runs go to Harness/.runtime/tieitup/bench/ and the
summary to PRDs and Specs/004 TieItUp/evidence/ only when a run completes.
SPEC.html section 06 is the specification.
"""
import argparse, concurrent.futures, datetime, hashlib, importlib.machinery, importlib.util, json, os, shutil, subprocess, sys, tempfile, time
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True        # nothing lands in the pinned clone
ROOT = Path(__file__).resolve().parents[1]
PONYTAIL = ROOT / "Harness" / "ponytail"
HARNESS = PONYTAIL / "benchmarks" / "agentic"
SKILL = ROOT / ".claude" / "skills" / "tieitup"
TIEITUP = ROOT / "Harness" / "bin" / "tieitup"
RUNTIME = ROOT / "Harness" / ".runtime" / "tieitup"
EVIDENCE = ROOT / "PRDs and Specs" / "004 TieItUp" / "evidence"
ARMS = ("ponytail", "ponytail2")      # each arm's plugin carries the arm's name
MODEL, OPUS = "opus", "claude-opus-5-5"
STOP_SHARE = 0.8                      # no new cell once spend reaches this share of --budget
AUTO_BUDGET = 5.0                     # an automatic pilot's stop line; the 15 October pilot spent $2.47
AUTO_EVERY_DAYS = 7                   # at most one automatic run a week, counted from the last attempt or result
WARM_COST = 0.32                      # the cold warm-up call, counted up front (run.py:326-328)
WORKERS = 2
HOOK_LOG = "_tieitup_hook.jsonl"      # underscore: the harness's LOC count skips it
ISOLATION = {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "quota")

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_harness = None
def harness():
    """The clone's run and compare modules, with TieItUp's tasks added to run.TASKS in memory."""
    global _harness
    if _harness is None:
        sys.path.insert(0, str(HARNESS))      # run.py imports tasks from its own folder
        run = _load("ponytail_bench_run", HARNESS / "run.py")
        run.TASKS.update(_load("tieitup_bench_tasks", ROOT / "Harness" / "tieitup-bench-tasks.py").TASKS)
        _harness = run, _load("ponytail_bench_compare", HARNESS / "compare.py")
    return _harness

def _retry(action, tries=10, pause=0.3):
    """On Windows a child killed without a wait holds its folder for a moment
    (tasks.py:574 kills the node server and returns), so a removal or move retries."""
    for attempt in range(tries):
        try: return action()
        except PermissionError:
            if attempt == tries - 1: raise
            time.sleep(pause)

class _PatientTemporaryDirectory(tempfile.TemporaryDirectory):
    def cleanup(self): _retry(super().cleanup)

def quick_tasks(run): return [t for t in run.QUICK if not run.TASKS[t].get("fixture")]
def hidden_tasks(run): return [t for t in quick_tasks(run) if not run.TASKS[t].get("open")]

def no_windows():
    """Every subprocess.Popen in this process, the harness's included, opens no window."""
    if os.name != "nt" or getattr(subprocess.Popen, "_no_window", False): return
    class NoWindowPopen(subprocess.Popen):
        _no_window = True
        def __init__(self, *args, **kwargs):
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)
    subprocess.Popen = NoWindowPopen

def run_cells(cells, run_one, stop_usd, workers=WORKERS, spent=0.0):
    """Run cells until done, the spend stop or a usage limit; list every cell left unrun."""
    results, pending, running, stop = [], list(cells), {}, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        while (pending and stop is None) or running:
            while pending and stop is None and len(running) < workers:
                if spent >= stop_usd:
                    stop = f"spend ${spent:.2f} reached the stop line ${stop_usd:.2f}"
                    break
                spec = pending.pop(0)
                running[pool.submit(run_one, spec)] = spec
            if not running: break
            done, _ = concurrent.futures.wait(running, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                task, arm, r = running.pop(future)
                try: result = future.result()
                except Exception as e:     # the runner's own failure is infrastructure, never a score
                    result = {"task": task, "arm": arm, "run": r, "error": str(e)[:300], "infra": "crash"}
                results.append(result)
                spent += result.get("cost") or 0
                if result.get("infra") == "usage-limit" and stop is None:
                    stop = f"usage-limit on {result.get('task')} / {result.get('arm')}"
    return {"results": results, "spent": round(spent, 4), "unrun": pending, "stop": stop}

def classify(ws, result):
    """The infrastructure failure a cell suffered, or None when it can be scored."""
    if result.get("error"): return "crash"
    err = Path(ws) / "_claude.stderr.txt"
    stderr = err.read_text(encoding="utf-8", errors="replace") if err.exists() else ""
    if "[KILLED after" in stderr: return "timeout"
    try:
        out = json.loads((Path(ws) / "_claude.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "crash"
    if not (out.get("is_error") or "error" in out): return None
    text = f"{out.get('result', '')} {out.get('error', '')} {stderr}".lower()
    return "usage-limit" if any(w in text for w in LIMIT_WORDS) else "crash"

def served_models(transcript):
    models = set()
    with open(transcript, encoding="utf-8", errors="replace") as f:
        for line in f:
            try: rec = json.loads(line)
            except ValueError: continue   # a torn last line is not a model record
            model = (rec.get("message") or {}).get("model") if rec.get("type") == "assistant" else None
            if model and not model.startswith("<"): models.add(model)   # skip <synthetic> notices
    return models

def served_by_opus(models): return bool(models) and all(m.startswith(OPUS) for m in models)

def cleanup_targets(config, home, appdata):
    """The top of the Claude config folder first, then the folders only Ponytail writes."""
    config = Path(config)
    targets = [config, config / "ponytail-modes", Path(home) / ".config" / "ponytail", Path(appdata) / "ponytail"]
    if os.environ.get("XDG_CONFIG_HOME"): targets.append(Path(os.environ["XDG_CONFIG_HOME"]) / "ponytail")
    return targets

def snapshot(targets): return {str(t): sorted(os.listdir(t)) if t.is_dir() else None for t in targets}

def _remove(path):
    if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
    else: path.unlink()

def clean_up(before):
    """Remove what appeared since the snapshot. At the top of the config folder only
    Ponytail's names go; anything else new there is listed as left, never deleted."""
    removed, left = [], []
    for i, (folder, names) in enumerate(before.items()):
        folder = Path(folder)
        if not folder.exists(): continue
        if names is None and i > 0:
            _remove(folder); removed.append(str(folder)); continue
        for name in sorted(set(os.listdir(folder)) - set(names or [])):
            path = folder / name
            if i == 0 and "ponytail" not in name.lower(): left.append(str(path)); continue
            _remove(path); removed.append(str(path))
    return removed, left

SESSION_HOOK = r'''import json, pathlib
text = (pathlib.Path(__file__).resolve().parent / "context.md").read_text(encoding="utf-8")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
'''
POST_EDIT_HOOK = r'''import json, os, pathlib, subprocess, sys
conf = json.loads((pathlib.Path(__file__).resolve().parent / "bench.json").read_text(encoding="utf-8"))
event = json.load(sys.stdin)
target = (event.get("tool_input") or {}).get("file_path")
if not target: sys.exit(0)
cwd = event.get("cwd") or os.getcwd()
out = subprocess.run([conf["python"], "-B", conf["tieitup"], "check", "--", target], cwd=cwd,
                     capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
                     stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
findings = [line for line in out.stdout.splitlines() if line.strip()]
with open(os.path.join(cwd, conf["log"]), "a", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps({"file": target, "findings": len(findings), "exit": out.returncode}) + "\n")
if findings:
    text = "tieitup check found:\n" + "\n".join(findings)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))
'''

def _write(path, text):
    """Write through a temp file and os.replace, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f: f.write(text)
    os.replace(tmp, path)

def build_plugin(dest, sources, python, tieitup):
    """The ponytail2 plugin: a session-start hook that injects sources, a post-edit hook
    that runs tieitup check. Absolute paths are fine here: the folder is untracked."""
    missing = [str(p) for p in sources if not Path(p).is_file()]
    if missing: sys.exit(f"cannot build the ponytail2 plugin, missing: {', '.join(missing)}")
    dest = Path(dest)
    if dest.exists(): shutil.rmtree(dest)
    hooks = dest / "hooks"
    _write(dest / ".claude-plugin" / "plugin.json", json.dumps({
        "name": "ponytail2", "version": "0.1.0", "hooks": "./hooks/bench-hooks.json",
        "description": "TieItUp benchmark arm: Ponytail, TieItUp and its Python pack, with tieitup check after each edit"}, indent=2))
    _write(hooks / "context.md", "\n\n".join(Path(p).read_text(encoding="utf-8") for p in sources))
    _write(hooks / "bench.json", json.dumps({"python": Path(python).as_posix(), "tieitup": Path(tieitup).as_posix(),
                                             "log": HOOK_LOG}, indent=2))
    _write(hooks / "session_start.py", SESSION_HOOK)
    _write(hooks / "post_edit.py", POST_EDIT_HOOK)
    def command(script): return f'"{Path(python).as_posix()}" -B "{(hooks / script).as_posix()}"'
    _write(hooks / "bench-hooks.json", json.dumps({"hooks": {
        "SessionStart": [{"matcher": "startup|resume|clear|compact",
                          "hooks": [{"type": "command", "command": command("session_start.py"), "timeout": 10}]}],
        "PostToolUse": [{"matcher": "Edit|Write|MultiEdit",
                         "hooks": [{"type": "command", "command": command("post_edit.py"), "timeout": 30}]}]}}, indent=2))
    return dest

def prepare_arms():
    sources = [PONYTAIL / "skills" / "ponytail" / "SKILL.md", SKILL / "SKILL.md", SKILL / "references" / "python.md"]
    if not TIEITUP.is_file(): sys.exit(f"missing {TIEITUP}")
    os.environ["PONYTAIL_PLUGIN_DIR"] = str(PONYTAIL)
    os.environ["PONYTAIL2_PLUGIN_DIR"] = str(build_plugin(RUNTIME / "plugin", sources, sys.executable, TIEITUP))

def dev_skills():
    folders = [ROOT / ".claude" / "skills", ROOT / ".agents" / "skills", Path.home() / ".claude" / "skills",
               Path.home() / ".agents" / "skills"]
    return {p.name for f in folders if f.is_dir() for p in f.iterdir()}

def isolate(run, dev, path):
    """Every session the harness starts turns dev's skills off; ~/.claude/skills links them in, and
    --setting-sources project,local (run.py:322) does not keep them out. In memory; the clone is untouched."""
    _write(path, json.dumps({"skillOverrides": {name: "off" for name in sorted(dev)}}, indent=2) + "\n")
    base = getattr(run._base_cmd, "_unisolated", run._base_cmd)
    def isolated(*args):
        return base(*args) + ["--settings", str(path)]
    isolated._unisolated = base
    run._base_cmd = isolated

def probe_command(run, claude, arm, plugin_dir):
    cmd = run._base_cmd(claude, "Reply with: ok", MODEL)
    cmd[cmd.index("--output-format") + 1] = "stream-json"
    return cmd + ["--verbose", "--plugin-dir", plugin_dir, "--append-system-prompt", run.NO_RUN]

def parse_probe(text, arm, dev):
    """(ok, problems, init record). Not checked against a real stream-json record."""
    init = None
    for line in text.splitlines():
        try: rec = json.loads(line)
        except ValueError: continue
        if isinstance(rec, dict) and rec.get("type") == "system" and rec.get("subtype") == "init":
            init = rec; break
    if init is None: return False, ["no init record"], None
    if "plugins" not in init or "skills" not in init:
        return False, ["the init record does not show plugins and skills"], init
    plugins = [p.get("name") if isinstance(p, dict) else p for p in init["plugins"] or []   # built in: same in both arms
               if not (isinstance(p, dict) and str(p.get("source", "")).endswith("@builtin"))]
    problems = [f"plugin {p} loaded beyond the arm's own" for p in plugins if p != arm]
    if arm not in plugins: problems.append(f"the arm's plugin {arm} did not load")
    for s in init["skills"] or []:
        name = s.get("name") if isinstance(s, dict) else str(s)
        if name.startswith(arm + ":"): continue
        if ":" in name or name in dev: problems.append(f"skill {name} leaked into the {arm} arm")
    if not str(init.get("model", "")).startswith(OPUS): problems.append(f"model {init.get('model')} is not {OPUS}")
    return not problems, problems, init

def summarise(rows, compare, quick, hidden, extra, runs):
    """Recompute the headline from raw rows; infrastructure failures are apart, never zeros."""
    infra = [{"task": r["task"], "arm": r["arm"], "run": r.get("run"), "kind": r["infra"]} for r in rows if r.get("infra")]
    cells = defaultdict(list)
    for r in rows:
        if not r.get("infra"): cells[(r["task"], r["arm"])].append(r)
    def agg(task, arm, metric):
        get, fn, _ = compare.METRICS[metric]
        values = [v for v in (get(c) for c in cells[(task, arm)]) if v is not None]
        return fn(values) if values else None
    def sign(metric, tasks):
        higher, wins, losses, ties = compare.METRICS[metric][2], 0, 0, 0
        for t in tasks:
            a, b = agg(t, "ponytail", metric), agg(t, "ponytail2", metric)
            if a is None or b is None: continue
            if a == b: ties += 1; continue
            if (b > a) == higher: wins += 1
            else: losses += 1
        return {"tasks": len(tasks), "wins": wins, "losses": losses, "ties": ties, "p": round(compare.sign_p(wins, losses), 4)}
    def passed(task, arm): return sum(1 for c in cells[(task, arm)] if c.get("correct") and c.get("safe"))
    phase = "pilot" if runs == 1 else "measurement"
    if phase == "pilot":
        rule = "TieItUp fails two or more of the hidden-check tasks that Ponytail passes"
        lost = [t for t in hidden if passed(t, "ponytail") and cells[(t, "ponytail2")] and not passed(t, "ponytail2")]
        regression = len(lost) >= 2
    else:
        rule = "a task where TieItUp passes two fewer cells, or a pass sign test favouring Ponytail at p < 0.05"
        lost = [t for t in hidden if passed(t, "ponytail") - passed(t, "ponytail2") >= 2]
        pass_sign = sign("pass", hidden)
        regression = bool(lost) or (pass_sign["p"] < 0.05 and pass_sign["losses"] > pass_sign["wins"])
    loc, cost = sign("loc", quick), sign("cost", quick)
    loc["better"] = loc["p"] < 0.05 and loc["wins"] > loc["losses"]
    cost["significant_rise"] = cost["p"] < 0.05 and cost["losses"] > cost["wins"]
    cost["significant_fall"] = cost["p"] < 0.05 and cost["wins"] > cost["losses"]
    headline = "; ".join(filter(None, [
        f"{phase}: lines of code over the {loc['tasks']} quick tasks, TieItUp {loc['wins']} wins and "
        f"{loc['losses']} losses, p={loc['p']:.3f}, " + ("better" if loc["better"] else "within noise"),
        f"cost per session {cost['wins']} cheaper and {cost['losses']} dearer, p={cost['p']:.3f}, " +
        ("a significant rise, a cost of TieItUp" if cost["significant_rise"] else
         "significantly lower" if cost["significant_fall"] else "within noise"),
        ("REGRESSION on hidden checks: " + ", ".join(lost)) if regression else
        f"no regression on the {len(hidden)} hidden-check tasks",
        f"{len(infra)} infrastructure failures, reported apart" if infra else ""]))
    return {"headline": headline, "phase": phase, "loc": loc, "cost": cost, "regression": regression,
            "quality": {"tasks": hidden, "rule": rule, "ponytail2_fails_ponytail_passes": lost,
                        "passed": {t: {a: passed(t, a) for a in ARMS} for t in hidden}},
            "tieitup_tasks": {t: {a: {"cells": len(cells[(t, a)]), "passed": passed(t, a), "loc": agg(t, a, "loc"),
                                      "cost": agg(t, a, "cost")} for a in ARMS} for t in extra},
            "infrastructure": infra,
            "engagement": [{k: r.get(k) for k in ("task", "arm", "run", "check_runs", "check_showed_findings",
                                                   "final_findings")} for r in rows if "final_findings" in r]}

def write_summary(summary, run_dir, evidence_dir, complete):
    _write(Path(run_dir) / "summary.json", json.dumps(summary, indent=2) + "\n")
    if not complete: return None
    path = Path(evidence_dir) / f"bench-{summary['date']}.json"
    _write(path, json.dumps(summary, indent=2) + "\n")
    return path

def _tieitup_check(files, cwd):
    if not files: return []
    out = subprocess.run([sys.executable, "-B", str(TIEITUP), "check", "--", *map(str, files)], cwd=str(cwd),
                         capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    return [line for line in out.stdout.splitlines() if line.strip()]

def run_one(run, spec, scratch, run_dir, config):
    """One cell through the harness, plus transcript, served model and tieitup check."""
    task, arm, r = spec
    name = f"{task}__{arm}__{MODEL}__{r}"
    ws = scratch / name
    ws.mkdir(parents=True)
    try:
        try: result = run.run_cell(task, arm, MODEL, ws)
        except Exception as e: result = {"task": task, "arm": arm, "model": MODEL, "error": str(e)[:300]}
        result["run"] = r
        kind = classify(ws, result)
        try: session = json.loads((ws / "_claude.json").read_text(encoding="utf-8")).get("session_id")
        except (OSError, ValueError): session = None
        transcripts = sorted(Path(config).glob(f"projects/*/{session}.jsonl")) if session else []
        if transcripts: shutil.copy2(transcripts[0], run_dir / f"{name}.jsonl")
        result["served_models"] = sorted(served_models(transcripts[0])) if transcripts else []
        if kind is None and not served_by_opus(result["served_models"]): kind = "not-opus"
        if kind: result["infra"] = kind
        log = ws / HOOK_LOG
        hook = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()] if log.exists() else []
        files = [p for p in ws.rglob("*") if p.is_file() and p.suffix in run.CODE_EXT and ".git" not in p.parts
                 and not p.name.startswith(("_", "."))]
        findings = _tieitup_check(files, ws)
        result.update(check_runs=len(hook), check_showed_findings=sum(1 for h in hook if h.get("findings")),
                      final_findings=len(findings), final_finding_lines=findings[:50])
        return result
    finally:
        _retry(lambda: shutil.move(str(ws), str(run_dir / name)))

def _git_head(path):
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

def fingerprint(claude_version):
    base = {"ponytail_commit": _git_head(PONYTAIL), "claude": claude_version, "model": OPUS}
    digest = hashlib.sha256()
    for p in sorted(p for p in SKILL.rglob("*") if p.is_file()) + [TIEITUP]:
        digest.update(p.relative_to(ROOT).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return {"ponytail": base, "ponytail2": {**base, "tieitup_sha256": digest.hexdigest()}}

def _config_dir(): return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
def _default_targets():
    return cleanup_targets(_config_dir(), Path.home(), os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")

def run_bench(run, compare, budget, runs):
    if not shutil.which("claude"): sys.exit("claude CLI not found on PATH")
    prepare_arms()
    isolate(run, dev_skills(), RUNTIME / "isolation.json")
    now = datetime.datetime.now()
    run_dir = RUNTIME / "bench" / "runs" / now.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)
    extra = [t for t in run.TASKS if t.startswith("tie-")]
    quick = quick_tasks(run)
    cells = [(t, arm, r) for r in range(runs) for t in quick + extra for arm in ARMS]
    scratch = Path(tempfile.mkdtemp(prefix="tieitup-bench-"))        # outside any repository (run.py:497-500)
    before = snapshot(_default_targets())
    try:
        run.warm_cache(MODEL)
        out = run_cells(cells, lambda c: run_one(run, c, scratch, run_dir, _config_dir()),
                        budget * STOP_SHARE, spent=WARM_COST)
    finally:
        removed, left = clean_up(before)
        shutil.rmtree(scratch, ignore_errors=True)
    _write(run_dir / "results.json", json.dumps({"results": out["results"]}, indent=2) + "\n")
    summary = {"date": now.strftime("%Y-%m-%d"), "fingerprint": fingerprint(run._claude_version()),
               **summarise(out["results"], compare, quick, hidden_tasks(run), extra, runs),
               "budget_usd": budget, "spent_usd": out["spent"], "stop": out["stop"],
               "unrun": [list(c) for c in out["unrun"]], "cleanup": {"removed": removed, "left": left}}
    complete = out["stop"] is None
    path = write_summary(summary, run_dir, EVIDENCE, complete)
    print(summary["headline"])
    for c in out["unrun"]: print(f"  not run: {c[0]} / {c[1]} #{c[2]}")
    print(f"raw runs: {run_dir}\nsummary: {path or 'not written to evidence/: ' + str(out['stop'])}")
    return 0 if complete else 1

def harness_drift():
    """What moved since the newest benchmark, as the tieitup command reads it (SPEC.html 06)."""
    loader = importlib.machinery.SourceFileLoader("tieitup_command", str(TIEITUP))   # no .py suffix
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod.harness_drift(ROOT)

def auto_decision(drift, last, today):
    """(run now?, why) for the automatic pilot the owner allowed on a harness move, within its cap."""
    if not drift or not (drift["version"] or drift["model"]):
        return False, "benchmark current for this harness; nothing to run"
    if drift["model"] and drift["model"][1] != OPUS:
        return False, (f"model {drift['model'][0]} -> {drift['model'][1]}: set OPUS in Harness/tieitup-bench.py "
                       "to the new model first, then run auto again")
    if last and (today - last).days < AUTO_EVERY_DAYS:
        return False, f"benchmark due, but the cap allows the next automatic run from {last + datetime.timedelta(AUTO_EVERY_DAYS)}"
    moved = "; ".join(f"{what} {drift[what][0]} -> {drift[what][1]}" for what in ("version", "model") if drift[what])
    return True, f"{moved}: automatic pilot, stop line ${AUTO_BUDGET:.2f}"

def auto(run, compare, today):
    """The automatic pilot: decide, record the attempt so a crash still counts against the cap, then run."""
    drift = harness_drift()
    state = RUNTIME / "bench" / "auto.json"
    dates = [datetime.date.fromisoformat(drift["bench"]["date"])] if drift else []
    try:
        dates.append(datetime.date.fromisoformat(json.loads(state.read_text(encoding="utf-8"))["last"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass                              # no earlier automatic run: the newest result alone counts
    go, why = auto_decision(drift, max(dates) if dates else None, today)
    print(f"tieitup-bench auto: {why}")
    if not go: return 0
    if selftest(): sys.exit("instruments broken; refusing to spend")
    _write(state, json.dumps({"version": 1, "last": today.isoformat(), "why": why}) + "\n")
    return run_bench(run, compare, AUTO_BUDGET, 1)

def probe(run):
    claude = shutil.which("claude") or sys.exit("claude CLI not found on PATH")
    prepare_arms()
    isolate(run, dev_skills(), RUNTIME / "isolation.json")
    out_dir = RUNTIME / "bench" / "probes"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp, failed = datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), 0
    before = snapshot(_default_targets())
    try:
        for arm in ARMS:
            with tempfile.TemporaryDirectory() as d:
                out = subprocess.run(probe_command(run, claude, arm, run._plugin_dir(arm)), cwd=d, capture_output=True,
                                     text=True, encoding="utf-8", errors="replace", timeout=run.CELL_TIMEOUT,
                                     env={**os.environ, **ISOLATION}, stdin=subprocess.DEVNULL)
            _write(out_dir / f"{stamp}-{arm}.jsonl", out.stdout)
            ok, problems, _ = parse_probe(out.stdout, arm, dev_skills())
            failed += not ok
            print(f"{'ok ' if ok else 'XX '} probe {arm}: " + ("; ".join(problems) or "only the arm's own plugin"))
    finally:
        removed, left = clean_up(before)
        print(f"clean-up removed {len(removed)}, left {left or 'nothing'}")
    return 1 if failed else 0

def selftest():
    run, compare = harness()
    original, tempfile.TemporaryDirectory = tempfile.TemporaryDirectory, _PatientTemporaryDirectory
    try: failures = run.selftest()
    finally: tempfile.TemporaryDirectory = original
    rows = [{"task": "csv-sum", "arm": "ponytail", "run": 0, "correct": 1, "safe": 1, "total_loc": 5},
            {"task": "csv-sum", "arm": "ponytail2", "run": 0, "error": "boom", "infra": "crash"}]
    s = summarise(rows, compare, ["csv-sum"], ["csv-sum"], [], 1)
    ok = s["infrastructure"] and not s["quality"]["ponytail2_fails_ponytail_passes"] and classify(".", {"error": "x"}) == "crash"
    print(f"{'ok ' if ok else 'XX '} infrastructure a crashed cell is reported apart, not as failed")
    failures += 0 if ok else 1
    print(f"tieitup-bench selftest: {'all instruments valid' if not failures else str(failures) + ' BROKEN'}")
    return failures

def main(argv=None):
    ap = argparse.ArgumentParser(description="TieItUp's benchmark on Ponytail's agentic harness")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="grade every hidden check, TieItUp's included; no model call")
    sub.add_parser("probe", help="one 'Reply with: ok' session per arm, showing what loaded (spends)")
    r = sub.add_parser("run", help="the benchmark (spends)")
    r.add_argument("--budget", type=float, required=True, help="stop line in USD; no new cell past 80%%")
    r.add_argument("--runs", type=int, default=1, help="cells per task and arm: 1 is the pilot")
    sub.add_parser("auto", help=f"the pilot, only after a harness move and at most every {AUTO_EVERY_DAYS} days (spends)")
    args = ap.parse_args(argv)
    no_windows()
    run, compare = harness()
    if args.command == "selftest": return 1 if selftest() else 0
    if args.command == "auto": return auto(run, compare, datetime.date.today())
    if selftest(): sys.exit("instruments broken; refusing to spend")
    if args.command == "probe": return probe(run)
    if args.budget <= 0 or args.runs < 1: sys.exit("--budget must be above 0 and --runs at least 1")
    return run_bench(run, compare, args.budget, args.runs)

if __name__ == "__main__":
    sys.exit(main())
