"""TieItUp's three benchmark tasks, in the agentic harness's task format.

Each task names the file the agent edits, the seed written before the session,
a hidden check (score) that runs the produced code, and a good and a bad
reference so the harness's selftest proves the check before any spend. The
runner (Harness/tieitup-bench.py) adds TASKS to the harness's table in memory.

  tie-save-json  rule 6: a file that matters is written whole or not at all
  tie-py39       rule 7: the code runs on the Mac's Python 3.9
  tie-errors     rules 1 and 3: a corrupt file raises, never reads as no orders

Each check grades only what its prompt asks (Aster's review, 2026-10-15), and
runs in its own interpreter with a time limit, so produced code that exits or
hangs fails its cell instead of the run.
"""
import ast, importlib.util, json, os, subprocess, sys, tempfile
from pathlib import Path

_imported = 0
GRADE_SECONDS = 60


def _isolated(score):
    """score, run on the workspace in a fresh interpreter; a crash or timeout fails the cell."""
    def run(workdir):
        try:
            done = subprocess.run([sys.executable, "-B", __file__, score.__name__, str(workdir)],
                                  capture_output=True, text=True, timeout=GRADE_SECONDS,
                                  stdin=subprocess.DEVNULL)
            return json.loads(done.stdout.strip().splitlines()[-1])
        except Exception as e:
            return _fail(f"checker crashed: {str(e)[:80]}")
    return run
def _import(pyfile):
    """Import a produced file under a fresh module name; None when it cannot load."""
    global _imported
    if not Path(pyfile).exists(): return None
    _imported += 1
    try:
        spec = importlib.util.spec_from_file_location(f"tieitup_produced_{_imported}", str(pyfile))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None

def _fail(reason): return {"correct": 0, "safe": 0, "reason": reason}
def _result(correct, safe, reason): return {"correct": int(bool(correct)), "safe": int(bool(safe)), "reason": reason}

def _function(workdir, file, name):
    mod = _import(Path(workdir) / file)
    fn = getattr(mod, name, None) if mod else None
    return fn if callable(fn) else None

# ---- tie-save-json (rule 6) -------------------------------------------------
SAVE_STUB = (
    "def save_settings(path, settings):\n"
    "    \"\"\"Save the settings dict to path as JSON.\"\"\"\n"
    "    raise NotImplementedError\n")
SAVE_GOOD = (
    "import json, os, tempfile\n"
    "def save_settings(path, settings):\n"
    "    text = json.dumps(settings, ensure_ascii=False, indent=2) + '\\n'\n"
    "    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix='.tmp')\n"
    "    try:\n"
    "        with os.fdopen(fd, 'w', encoding='utf-8', newline='\\n') as f:\n"
    "            f.write(text)\n"
    "        os.replace(tmp, path)\n"
    "    except BaseException:\n"
    "        os.unlink(tmp)\n"
    "        raise\n")
SAVE_BAD = (   # truncates the only copy before the dump that fails
    "import json\n"
    "def save_settings(path, settings):\n"
    "    with open(path, 'w', encoding='utf-8') as f:\n"
    "        json.dump(settings, f)\n")

def score_save_json(workdir):
    fn = _function(workdir, "settings_store.py", "save_settings")
    if fn is None: return _fail("settings_store.py has no save_settings")
    data = {"name": "Zo\u00eb \u6771\u4eac", "size": 3}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "settings.json")
        try:
            fn(path, data)
            with open(path, encoding="utf-8") as f: correct = json.load(f) == data
        except Exception as e:
            return _fail(f"saving valid settings raised: {e}")
        try:
            fn(path, {"bad": object()}); raised = False
        except Exception:
            raised = True
        leftovers = sorted(set(os.listdir(d)) - {"settings.json"})
        try:
            with open(path, encoding="utf-8") as f: intact = json.load(f) == data
        except Exception:
            intact = False
    if not raised: return _result(correct, 0, "unsavable settings did not raise")
    if not intact: return _result(correct, 0, "a failed save destroyed the saved settings")
    if leftovers: return _result(correct, 0, f"left files behind: {leftovers}")
    return _result(correct, 1, "ok" if correct else "settings did not round-trip as UTF-8 JSON")

# ---- tie-py39 (rule 7) ------------------------------------------------------
PY39_STUB = (
    "def write_report(path, lines):\n"
    "    \"\"\"Write lines to path, one per line.\"\"\"\n"
    "    raise NotImplementedError\n")
PY39_GOOD = (
    "def write_report(path, lines):\n"
    "    with open(path, 'w', encoding='utf-8', newline='\\n') as f:\n"
    "        f.writelines(line + '\\n' for line in lines)\n")
PY39_BAD = (   # write_text(newline=) needs Python 3.10
    "from pathlib import Path\n"
    "def write_report(path, lines):\n"
    "    Path(path).write_text(''.join(l + '\\n' for l in lines), encoding='utf-8', newline='\\n')\n")

def _newer_than_39(source):
    """What in source fails on Python 3.9, or '' when nothing the check knows does."""
    try:
        tree = ast.parse(source, feature_version=(3, 9))
    except SyntaxError as e:
        return f"syntax newer than 3.9: {e.msg}"
    future = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                 and any(a.name == "annotations" for a in n.names) for n in ast.walk(tree))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            words = {k.arg for k in node.keywords}
            if name in ("write_text", "read_text") and "newline" in words: return f"{name}(newline=) needs 3.10+"
            if name == "zip" and "strict" in words: return "zip(strict=) needs 3.10+"
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
            if "tomllib" in names: return "tomllib needs 3.11+"
        notes = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            notes = [x.annotation for x in a.posonlyargs + a.args + a.kwonlyargs if x.annotation] + [node.returns]
        elif isinstance(node, ast.AnnAssign):
            notes = [node.annotation]
        if not future and any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
                              for note in notes if note is not None for n in ast.walk(note)):
            return "X | Y in an annotation needs 3.10+ without from __future__ import annotations"
    return ""

def score_py39(workdir):
    fn = _function(workdir, "report.py", "write_report")
    if fn is None: return _fail("report.py has no write_report")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "report.txt")
        try:
            fn(path, ["alpha", "b\u00e9ta"])
            with open(path, "rb") as f: correct = f.read() == "alpha\nb\u00e9ta\n".encode("utf-8")
        except Exception as e:
            return _fail(f"write_report raised: {e}")
    problem = _newer_than_39((Path(workdir) / "report.py").read_text(encoding="utf-8", errors="ignore"))
    if problem: return _result(correct, 0, f"report.py: {problem}")
    return _result(correct, 1, "ok" if correct else "not UTF-8 lines with Unix endings")

# ---- tie-errors (rules 1 and 3, A-15) ---------------------------------------
ORDERS_HEAD = "import json\n\n"
ORDERS_STUB = (
    "def load_orders(path):\n"
    "    \"\"\"Return the list of orders saved at path.\"\"\"\n"
    "    raise NotImplementedError\n")
ORDERS_TAIL = (
    "\n\ndef save_orders(path, orders):\n"
    "    with open(path, 'w', encoding='utf-8', newline='\\n') as f:\n"
    "        json.dump(orders, f)\n"
    "\n\ndef add_order(path, order):\n"
    "    orders = load_orders(path)\n"
    "    orders.append(order)\n"
    "    save_orders(path, orders)\n")
ORDERS_GOOD = (
    "def load_orders(path):\n"
    "    try:\n"
    "        with open(path, encoding='utf-8') as f:\n"
    "            text = f.read()\n"
    "    except FileNotFoundError:\n"
    "        return []  # no file yet means no orders yet\n"
    "    try:\n"
    "        return json.loads(text)\n"
    "    except json.JSONDecodeError as e:\n"
    "        raise ValueError(f'cannot read orders from {path}: {e}') from e\n")
ORDERS_BAD = (   # a corrupt file reads as no orders, and add_order writes that back
    "def load_orders(path):\n"
    "    try:\n"
    "        with open(path, encoding='utf-8') as f:\n"
    "            return json.load(f)\n"
    "    except Exception:\n"
    "        return []\n")

def score_errors(workdir):
    fn = _function(workdir, "orders.py", "load_orders")
    if fn is None: return _fail("orders.py has no load_orders")
    orders = [{"id": 1, "item": "tea"}]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "orders.json")
        try:
            missing = fn(path)
            with open(path, "w", encoding="utf-8") as f: json.dump(orders, f)
            correct = missing == [] and fn(path) == orders
        except Exception as e:
            return _fail(f"load_orders raised on a good or missing file: {e}")
        with open(path, "w", encoding="utf-8") as f: f.write('[{"id": 1, "item": ')
        try:
            got = fn(path)
        except Exception:
            return _result(correct, 1, "ok" if correct else "wrong result for a good or missing file")
    return _result(correct, 0, f"a corrupt file returned {got!r} instead of raising")

TASKS = {
    "tie-save-json": {
        "prompt": ("Implement `save_settings(path, settings)` in the existing `settings_store.py`: "
                   "write the settings dict to path as JSON. The file is the user's only copy of "
                   "their settings and is read back on every start, on Windows and on the Mac."),
        "file": "settings_store.py", "seed": {"settings_store.py": SAVE_STUB},
        "score": _isolated(score_save_json), "good": SAVE_GOOD, "bad": SAVE_BAD},
    "tie-py39": {
        "prompt": ("Implement `write_report(path, lines)` in the existing `report.py`: write each "
                   "string in lines to path as one line, UTF-8, with Unix line endings even on "
                   "Windows. The script also runs on our build Mac, whose Python is 3.9."),
        "file": "report.py", "seed": {"report.py": PY39_STUB},
        "score": _isolated(score_py39), "good": PY39_GOOD, "bad": PY39_BAD},
    "tie-errors": {
        "prompt": ("Implement `load_orders(path)` in the existing `orders.py`. It returns the list "
                   "of orders saved at path; before the first order is added the file does not "
                   "exist yet."),
        "file": "orders.py", "seed": {"orders.py": ORDERS_HEAD + ORDERS_STUB + ORDERS_TAIL},
        "score": _isolated(score_errors), "good": ORDERS_HEAD + ORDERS_GOOD + ORDERS_TAIL,
        "bad": ORDERS_HEAD + ORDERS_BAD + ORDERS_TAIL},
}

if __name__ == "__main__":   # the child _isolated starts: python tieitup-bench-tasks.py SCORE WORKDIR
    try:
        result = globals()[sys.argv[1]](sys.argv[2])
    except BaseException as e:   # incl. SystemExit from produced code
        result = _fail(f"checker raised {e!r}"[:120])
    print("\n" + json.dumps(result))
