#!/usr/bin/env python3
"""The book library as page-marked Markdown; books runs this in Harness/.runtime/books.

  books.py build  [--library DIR] [--out DIR] [--only TEXT] [--cpu]
  books.py status [--library DIR] [--out DIR]
  books.py check  [--library DIR] [--out DIR] [--full]
  books.py page   BOOK N [-o PNG] [--library DIR]

A page keeps its text layer when that reads cleanly, else it is OCR'd. Pages
are appended to <title>.md.partial, and a sidecar records the last whole page,
so a stopped build resumes at the next one. Only new or changed PDFs are
converted. pypdfium2 and RapidOCR are imported inside functions, so the rest
is testable with any Python 3.9 or later.
Design: Setup/superpowers/specs/2026-09-25-books-as-markdown-design.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Harness"))
import common  # noqa: E402


def book_folder() -> Path:
    """PDF-file in the owner's book clone: a row of ~/.config/devarness/personal-repos.txt, never named in git."""
    for clone in common.pinned_clones(ROOT):
        if clone.personal and (ROOT / clone.path / "PDF-file").is_dir():
            return ROOT / clone.path / "PDF-file"
    return ROOT / "Harness" / "book-pdfs" / "PDF-file"   # none on this device: an empty library


LIBRARY = book_folder()
OUT = ROOT / "Books" / "text"
STATE = ".books.json"
LOCK = ".books.lock"
MIN_CHARS = 20        # fewer non-space characters than this is not a page of text
MIN_READABLE = 0.85   # the glyph-code books' sampled pages read 24% to 73%
RENDER_SCALE = 2      # twice the page size, as the OCR measurements used
MARKER = re.compile(r"^=====PAGE (\d+)=====$", re.M)
READABLE = ((0x20, 0x7E), (0xA0, 0xFF), (0x370, 0x3FF), (0x2000, 0x206F), (0x2190, 0x22FF),
            (0x2500, 0x257F), (0x3000, 0x303F), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xFF00, 0xFFEF))


MIN_SPACED = 3        # runs like "T C P" on one page: a layer that stores English letter by letter
MIN_ODD = 5           # characters outside these books' scripts on one page: glyph-code Chinese
RULE = 2              # the page rule; a book converted under an older one is read again once
SPACED = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z0-9] ){2,}[A-Za-z0-9](?![A-Za-z0-9])")
# The scripts these books use, for counting odd characters: Latin-1 letters count, since
# glyph-code garbage lands there; private-use glyphs, fonts' bullets, do not.
FINE = ((0x20, 0x7E), (0xA0, 0xBF), (0xD7, 0xD7), (0xF7, 0xF7), (0x370, 0x3FF), (0x2000, 0x206F),
        (0x2190, 0x22FF), (0x2500, 0x257F), (0x3000, 0x303F), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
        (0xFF00, 0xFFEF), (0xFFFE, 0xFFFE), (0xE000, 0xF8FF))


def readable(text: str) -> bool:
    """Rule 1: enough characters, most of them recognisable."""
    chars = [c for c in text if not c.isspace()]
    good = sum(1 for c in chars if any(low <= ord(c) <= high for low, high in READABLE))
    return len(chars) >= MIN_CHARS and good >= MIN_READABLE * len(chars)


def odd(c: str) -> bool:
    return not c.isspace() and not any(low <= ord(c) <= high for low, high in FINE)


def usable(text: str) -> bool:
    """Whether a text layer reads cleanly. Rule 2 (2026-09-27, the owner's option 1) also sends
    to OCR a page spelled out letter by letter and one carrying glyph-code garbage: both read
    over 85% and failed the accuracy sample of 2026-09-25."""
    return (readable(text) and len(SPACED.findall(text)) < MIN_SPACED
            and sum(1 for c in text if odd(c)) < MIN_ODD)


def block(number: int, text: str) -> str:
    return "=====PAGE %d=====\n\n%s\n\n" % (number, text.strip())


def sidecar(partial: Path) -> Path:
    return partial.with_name(partial.name + ".json")


def fresh() -> dict:
    return {"pages": 0, "bytes": 0, "text": 0, "ocr": 0, "low": [], "errors": {},
            "score": 0.0, "scored": 0}


def resume(partial: Path) -> dict:
    """What a partial already holds whole; cuts a torn last page. No sidecar: start over."""
    try:
        done = {**fresh(), **json.loads(sidecar(partial).read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        done = fresh()
    if not partial.exists() or partial.stat().st_size < done["bytes"]:
        done = fresh()
    partial.parent.mkdir(parents=True, exist_ok=True)
    with partial.open("ab") as handle:
        handle.truncate(done["bytes"])
    return done


def append(partial: Path, done: dict, number: int, text: str) -> None:
    """Add one page, and only then record it as whole."""
    with partial.open("ab") as handle:
        handle.write(block(number, text).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
        done["bytes"] = handle.tell()
    done["pages"] = number
    temporary = sidecar(partial).with_suffix(".tmp")
    temporary.write_text(json.dumps(done), encoding="utf-8")
    os.replace(temporary, sidecar(partial))


def load_state(out: Path) -> dict:
    try:
        state = json.loads((out / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.setdefault("books", {})
    state.setdefault("unreadable", {})
    return state


def save_state(out: Path, state: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    temporary = out / (STATE + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True),
                         encoding="utf-8")
    os.replace(temporary, out / STATE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target(out: Path, key: str) -> Path:
    return out / Path(key).with_suffix(".md")


def plan(library: Path, out: Path, state: dict) -> tuple:
    """(keys to convert, keys gone upstream). A PDF is hashed only when its size or time moved."""
    todo, present = [], set()
    for pdf in sorted(library.rglob("*.pdf")) if library.is_dir() else []:
        key = pdf.relative_to(library).as_posix()
        present.add(key)
        stat = pdf.stat()
        seen = state["books"].get(key) or state["unreadable"].get(key)
        if seen and (seen["size"], seen["mtime"]) != (stat.st_size, stat.st_mtime_ns):
            if seen["sha256"] == sha256(pdf):          # touched, not changed: a checkout does that
                seen["size"], seen["mtime"] = stat.st_size, stat.st_mtime_ns
        current = bool(seen) and (seen["size"], seen["mtime"]) == (stat.st_size, stat.st_mtime_ns)
        if not (current and (key in state["unreadable"] or target(out, key).exists())):
            todo.append(key)
    gone = sorted(key for key in {*state["books"], *state["unreadable"]} if key not in present)
    return todo, gone


def forget(out: Path, state: dict, key: str) -> None:
    state["books"].pop(key, None)
    state["unreadable"].pop(key, None)
    md = target(out, key)
    partial = md.with_name(md.name + ".partial")
    for path in (md, partial, sidecar(partial)):
        path.unlink(missing_ok=True)


def header(source_path: str, key: str, pages: int, text_pages: int, ocr_pages: int,
           engine: str, day: str) -> str:
    return ("# %s\n\n> **%s** · books · `current`\n>\n"
            "> Machine-extracted text of `%s`, %d pages: %d from the text layer,\n"
            "> %d by OCR (%s). Page markers are the PDF's page numbers. Check a\n"
            "> quote against the page image first: `books page \"%s\" <page>`.\n\n"
            % (Path(key).stem, day, source_path, pages, text_pages, ocr_pages, engine,
               Path(key).with_suffix("").as_posix()))


class Reader:
    """RapidOCR on the fastest provider here: DirectML on Windows, CoreML on a Mac, else the CPU."""

    def __init__(self, cpu: bool = False):
        from importlib.metadata import version
        import onnxruntime
        from rapidocr import RapidOCR
        params = {"EngineConfig.onnxruntime.intra_op_num_threads": 4}
        wanted = None
        if not cpu and sys.platform == "win32":
            params["EngineConfig.onnxruntime.use_dml"] = True
            wanted = ("DmlExecutionProvider", "DirectML")
        elif not cpu and sys.platform == "darwin":
            params["EngineConfig.onnxruntime.use_coreml"] = True
            wanted = ("CoreMLExecutionProvider", "CoreML")
        found = bool(wanted) and wanted[0] in onnxruntime.get_available_providers()
        self.name = "RapidOCR %s on %s" % (version("rapidocr"), wanted[1] if found else "the CPU")
        self.engine = RapidOCR(params=params)

    def __call__(self, image) -> tuple:
        result = self.engine(image)
        scores = list(result.scores or ())
        return "\n".join(result.txts or ()), (sum(scores) / len(scores) if scores else 0.0)

    def working(self) -> bool:
        """Whether the engine still answers: a blank page has nothing to find, and must not raise."""
        from PIL import Image
        try:
            self.engine(Image.new("RGB", (64, 64), "white"))
        except Exception:
            return False
        return True


def convert(doc, md: Path, reader, source_path: str, key: str, day: str) -> dict:
    """One book, page by page, resuming its partial; returns what the state records."""
    partial = md.with_name(md.name + ".partial")
    done = resume(partial)
    for index in range(done["pages"], len(doc)):
        number = index + 1
        try:
            page = doc[index]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            textpage.close()
            if usable(text):
                done["text"] += 1
            else:
                done["ocr"] += 1
                text, score = reader(page.render(scale=RENDER_SCALE).to_pil()) if reader else ("", 0.0)
                if score:
                    done["score"] += score
                    done["scored"] += 1
            page.close()
        except Exception as error:      # one bad page must not stop a 900-page book; it is recorded
            if reader and not reader.working():
                # Unless OCR itself broke, as DirectML does when it loses the GPU: every later page
                # would be blank, so the book stops here and this page is redone on the next run.
                raise RuntimeError("OCR stopped working at %s page %d: %s" % (key, number, error)) from error
            text = ""
            done["errors"][str(number)] = str(error)[:200]
        if len("".join(text.split())) < MIN_CHARS:
            done["low"].append(number)
        append(partial, done, number, text)
    engine = reader.name if reader else "no OCR"
    temporary = md.with_name(md.name + ".tmp")
    temporary.write_text(header(source_path, key, len(doc), done["text"], done["ocr"], engine, day)
                         + partial.read_text(encoding="utf-8"), encoding="utf-8")
    os.replace(temporary, md)
    partial.unlink()
    sidecar(partial).unlink(missing_ok=True)
    return {"pages": len(doc), "text_pages": done["text"], "ocr_pages": done["ocr"],
            "low_pages": done["low"], "page_errors": done["errors"],
            "ocr_confidence": round(done["score"] / done["scored"], 3) if done["scored"] else None}


def flipped_pages(doc) -> list:
    """The pages rule 1 took from the text layer and rule 2 sends to OCR."""
    flipped = []
    for index in range(len(doc)):
        try:
            page = doc[index]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            textpage.close()
            page.close()
        except Exception:
            continue                    # a page that would not load was recorded when converted
        if readable(text) and not usable(text):
            flipped.append(index + 1)
    return flipped


def repair(doc, md: Path, reader, numbers: list, entry: dict, source_path: str, key: str, day: str) -> dict:
    """Read the flipped pages again by OCR and put their text in place of the old blocks, whole
    or not at all, so a book's other pages, and its OCR, are not done twice. Returns the state
    fields that change; the confidence is weighted by the OCR pages already there."""
    parts = MARKER.split(md.read_text(encoding="utf-8"))          # header, number, body, number, body, ...
    bodies = dict(zip(parts[1::2], parts[2::2]))
    low, errors = set(entry.get("low_pages", [])), dict(entry.get("page_errors", {}))
    total, scored = 0.0, 0
    for number in numbers:
        try:
            page = doc[number - 1]
            text, score = reader(page.render(scale=RENDER_SCALE).to_pil())
            page.close()
        except Exception as error:
            if not reader.working():
                raise RuntimeError("OCR stopped working at %s page %d: %s" % (key, number, error)) from error
            text, score = "", 0.0
            errors[str(number)] = str(error)[:200]
        if score:
            total, scored = total + score, scored + 1
        if len("".join(text.split())) < MIN_CHARS:
            low.add(number)
        else:
            low.discard(number)
        bodies[str(number)] = block(number, text)[len("=====PAGE %d=====" % number):]
    text_pages, ocr_pages = entry["text_pages"] - len(numbers), entry["ocr_pages"] + len(numbers)
    before = entry.get("ocr_confidence")
    weight = entry["ocr_pages"] if before is not None else 0
    confidence = ((before or 0.0) * weight + total) / (weight + scored) if weight + scored else before
    temporary = md.with_name(md.name + ".tmp")
    temporary.write_text(header(source_path, key, entry["pages"], text_pages, ocr_pages, reader.name, day)
                         + "".join("=====PAGE %s=====%s" % (n, bodies[n]) for n in parts[1::2]),
                         encoding="utf-8")
    os.replace(temporary, md)
    return {"text_pages": text_pages, "ocr_pages": ocr_pages, "low_pages": sorted(low),
            "page_errors": errors, "ocr_confidence": round(confidence, 3) if confidence is not None else None}


def pid_alive(pid: int) -> bool:
    """update-tools's check, so the two locks agree on what a live process is."""
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    loader = SourceFileLoader("update_tools", str(ROOT / "Harness" / "bin" / "update-tools"))
    module = module_from_spec(spec_from_loader("update_tools", loader))
    loader.exec_module(module)
    return module.pid_alive(pid)


def acquire(out: Path):
    """None when this build now holds the lock; the holder's pid when a live build does."""
    out.mkdir(parents=True, exist_ok=True)
    lock = out / LOCK
    for _ in range(2):
        try:
            handle = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(lock.read_text(encoding="utf-8").strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and pid != os.getpid() and pid_alive(pid):
                return pid
            lock.unlink(missing_ok=True)        # its build died without releasing it
            continue
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        return None
    return "unknown"


def release(out: Path) -> None:
    (out / LOCK).unlink(missing_ok=True)


def lower_priority() -> None:
    """Below normal, so a build never competes with the owner's own work."""
    if os.name == "nt":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000)    # BELOW_NORMAL_PRIORITY_CLASS
    else:
        os.nice(10)


def source(pdf: Path) -> str:
    """The PDF's path as a reader in dev would type it."""
    try:
        return pdf.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return pdf.as_posix()


def write_index(out: Path, state: dict) -> None:
    rows, pages, low = [], 0, 0
    for key, entry in sorted(state["books"].items()):
        pages += entry["pages"]
        low += len(entry["low_pages"])
        rows.append("| %s | [%s](<%s>) | %d | %d | %d | %d |" % (
            Path(key).parent.as_posix(), Path(key).stem, Path(key).with_suffix(".md").as_posix(),
            entry["pages"], entry["text_pages"], entry["ocr_pages"], len(entry["low_pages"])))
    unreadable = ["- `%s`: %s" % (key, entry["error"]) for key, entry in sorted(state["unreadable"].items())]
    text = ("# The book library as Markdown: %d books, %d pages\n\n"
            "> **%s** · books · `current`\n>\n"
            "> Generated by `books build`, git-ignored and never synced. %d pages are\n"
            "> low-yield (%.1f%%). Grep this folder by its path, and check a quote with\n"
            "> `books page`.\n\n"
            "| Subject | Book | Pages | Text layer | OCR | Low-yield |\n"
            "| --- | --- | --- | --- | --- | --- |\n%s\n\n## Unreadable PDFs\n\n%s\n") % (
        len(rows), pages, time.strftime("%Y-%m-%d"), low, 100.0 * low / pages if pages else 0.0,
        "\n".join(rows), "\n".join(unreadable) or "None.")
    temporary = out / "INDEX.md.tmp"
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, out / "INDEX.md")


def build(library: Path, out: Path, only, cpu: bool) -> int:
    if not library.is_dir():
        print("books: no library at %s on this device; nothing to build" % library)
        return 0
    holder = acquire(out)
    if holder:
        print("books: a build is running (pid %s); nothing done" % holder)
        return 0
    try:
        import pypdfium2 as pdfium
        lower_priority()
        state = load_state(out)
        todo, gone = plan(library, out, state)
        for key in gone:
            forget(out, state, key)
        reader, converted, repaired, day = None, 0, 0, time.strftime("%Y-%m-%d")
        # A book converted under an older page rule is read again once, on every device: only
        # its flipped pages, by OCR, in place. A book with none just takes the new rule's stamp.
        for key, entry in sorted(state["books"].items()):
            if key in todo or entry.get("rule", 1) >= RULE or (only and only not in key):
                continue
            pdf = library / key
            try:
                doc = pdfium.PdfDocument(str(pdf))
            except pdfium.PdfiumError:
                continue                # its bytes changed or broke: plan() and the next build say so
            try:
                numbers = flipped_pages(doc)
                if numbers:
                    reader = reader or Reader(cpu)
                    entry.update(repair(doc, target(out, key), reader, numbers, entry, source(pdf), key, day))
            finally:
                doc.close()
            entry["rule"] = RULE
            save_state(out, state)
            if numbers:
                write_index(out, state)
                repaired += 1
                print("repaired %s: %d pages read again by OCR" % (key, len(numbers)), flush=True)
        for key in [k for k in todo if not only or only in k]:
            pdf = library / key
            stat = pdf.stat()
            entry = {"size": stat.st_size, "mtime": stat.st_mtime_ns, "sha256": sha256(pdf), "rule": RULE}
            try:
                doc = pdfium.PdfDocument(str(pdf))
            except pdfium.PdfiumError as error:
                state["books"].pop(key, None)
                state["unreadable"][key] = {**entry, "error": str(error)[:200]}
                save_state(out, state)
                print("unreadable %s: %s" % (key, error), flush=True)
                continue
            try:
                reader = reader or Reader(cpu)
                entry.update(convert(doc, target(out, key), reader, source(pdf), key, day))
            finally:
                doc.close()
            entry["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            state["unreadable"].pop(key, None)
            state["books"][key] = entry
            save_state(out, state)
            write_index(out, state)
            converted += 1
            print("converted %s: %d pages, %d by OCR" % (key, entry["pages"], entry["ocr_pages"]), flush=True)
        save_state(out, state)
        write_index(out, state)
        print("books: %d converted, %d repaired, %d removed, %d unreadable"
              % (converted, repaired, len(gone), len(state["unreadable"])))
        return 0
    finally:
        release(out)


def summary(library: Path, out: Path) -> dict:
    state = load_state(out)
    pdfs = {p.relative_to(library).as_posix() for p in library.rglob("*.pdf")} if library.is_dir() else set()
    done = sorted(k for k in state["books"] if k in pdfs and target(out, k).exists())
    unreadable = sorted(k for k in state["unreadable"] if k in pdfs)
    building = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.md.partial")) if out.is_dir() else []
    shelf = [state["books"][k] for k in done]
    return {"library": library.is_dir(), "readable": len(pdfs) - len(unreadable), "converted": len(done),
            "unreadable": unreadable, "building": building,
            "pages": sum(b["pages"] for b in shelf), "ocr": sum(b["ocr_pages"] for b in shelf),
            "low": sum(len(b["low_pages"]) for b in shelf),
            "errors": sum(len(b.get("page_errors", {})) for b in shelf)}


def status(library: Path, out: Path) -> int:
    s = summary(library, out)
    if not s["library"]:
        print("books: no library at %s on this device" % library)
        return 1
    print("converted  %d of %d readable PDFs; %d unreadable" % (s["converted"], s["readable"], len(s["unreadable"])))
    print("pages      %d, %d by OCR, %d low-yield (%.1f%%), %d page errors" % (
        s["pages"], s["ocr"], s["low"], 100.0 * s["low"] / s["pages"] if s["pages"] else 0.0, s["errors"]))
    for key in s["building"]:
        print("building   %s" % key)
    for key in s["unreadable"]:
        print("unreadable %s" % key)
    if s["errors"]:
        print("a book with page errors is redone by deleting its .md and running books build")
    return 0 if s["converted"] == s["readable"] and not s["building"] else 1


def check(library: Path, out: Path, full: bool) -> int:
    try:
        import pypdfium2 as pdfium
        import rapidocr  # noqa: F401 -- the runtime is whole
    except ImportError as error:
        print("books check: the runtime is missing (%s); run books install" % error)
        return 1
    problems = []
    state = load_state(out)
    for key, entry in sorted(state["books"].items()) if full else []:
        md = target(out, key)
        if not md.exists():
            problems.append("%s: its Markdown is missing" % key)
            continue
        numbers = [int(n) for n in MARKER.findall(md.read_text(encoding="utf-8"))]
        if numbers != list(range(1, entry["pages"] + 1)):
            problems.append("%s: %d page markers for %d pages" % (key, len(numbers), entry["pages"]))
        if (library / key).exists():
            doc = pdfium.PdfDocument(str(library / key))
            if len(doc) != entry["pages"]:
                problems.append("%s: the PDF has %d pages, the record %d" % (key, len(doc), entry["pages"]))
            doc.close()
    for problem in problems:
        print(problem)
    print("books check: %d problem(s)" % len(problems))
    return 1 if problems else 0


def page(library: Path, book: str, number: int, output) -> int:
    """Render one page to a PNG, so a quote can be checked against it."""
    import pypdfium2 as pdfium
    key = book.replace(chr(92), "/")
    for prefix in ("Books/text/", "PDF-file/"):
        key = key.split(prefix)[-1]
    if key.endswith((".md", ".pdf")):
        key = key.rsplit(".", 1)[0]
    pdf = library / (key + ".pdf")
    if not pdf.is_file():
        print("books: no such book: %s" % pdf)
        return 2
    doc = pdfium.PdfDocument(str(pdf))
    try:
        if not 1 <= number <= len(doc):
            print("books: %s has pages 1 to %d" % (key, len(doc)))
            return 2
        png = Path(output) if output else (
            Path(tempfile.gettempdir()) / "books" / ("%s-p%d.png" % (Path(key).name, number)))
        png.parent.mkdir(parents=True, exist_ok=True)
        doc[number - 1].render(scale=RENDER_SCALE).to_pil().save(png)
    finally:
        doc.close()
    print(png)
    return 0


def main(argv=None) -> int:
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    commands = {name: sub.add_parser(name) for name in ("build", "status", "check", "page")}
    for name, command in commands.items():
        command.add_argument("--library", default=str(LIBRARY))
        if name != "page":
            command.add_argument("--out", default=str(OUT))
    commands["build"].add_argument("--only", help="convert only books whose path contains this")
    commands["build"].add_argument("--cpu", action="store_true", help="OCR on the CPU even with a GPU")
    commands["check"].add_argument("--full", action="store_true", help="count every book's page markers")
    commands["page"].add_argument("book")
    commands["page"].add_argument("number", type=int)
    commands["page"].add_argument("-o", "--output")
    args = parser.parse_args(argv)
    library = Path(args.library)
    if args.command == "page":
        return page(library, args.book, args.number, args.output)
    out = Path(args.out)
    if args.command == "build":
        return build(library, out, args.only, args.cpu)
    if args.command == "status":
        return status(library, out)
    return check(library, out, args.full)


if __name__ == "__main__":
    sys.exit(main())
