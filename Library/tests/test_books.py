"""books: the readability rule, resumable pages, the incremental plan,
the launcher, and a real build on fixture PDFs.

Tests that need the runtime (`books install`) skip without it and say so.
None touches the real library or the real Books/text/.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


books = load("books", ROOT / "Library" / "books.py")

# A sampled page of 基于MVC的JavaScript_Web富应用开发, whose Chinese is stored as glyph codes.
GLYPH_CODES = "മჾȘixӱૌੰࢅ٪ئఇӱݛڦ๕Ǆ๑ᆩႜాႚ๕٪ئఇӱĂ๑ᆩ" * 3
CLEAN = "另一方面，如果使用异常替代返回错误码，错误处理代码就能从主路径代码中分离出来，得到简化。"
# Written like the TCP/IP books' text layer: three runs of letters or digits split by single spaces.
SPACED = CLEAN + "但 T C P / I P协议是 ( I n t e r n e t ) 的基础，超过1 0 0万台主机。"
TWO_RUNS = CLEAN + "但 T C P / I P协议是 ( I n t e r n e t ) 的基础。"


class Readability(unittest.TestCase):
    def test_glyph_codes_are_not_text(self):
        self.assertFalse(books.usable(GLYPH_CODES))

    def test_clean_chinese_is_text(self):
        self.assertTrue(books.usable(CLEAN))

    def test_a_few_characters_are_not_a_page(self):
        self.assertFalse(books.usable("42"))

    def test_go_assembly_with_middle_dots_is_text(self):
        self.assertTrue(books.usable("CALL runtime·args(SB)\nMOVQ $0, AX\nCALL runtime·osinit(SB)"))

    # Rule 2, the owner's option 1 (2026-09-27): the accuracy sample found text layers
    # that store English letter by letter and Chinese as glyph codes, yet read over 85%.
    def test_a_page_spelled_letter_by_letter_goes_to_ocr(self):
        self.assertTrue(books.readable(SPACED))
        self.assertFalse(books.usable(SPACED))
        self.assertTrue(books.usable(TWO_RUNS), "two spaced runs are not yet a spaced page")

    def test_a_page_with_glyph_codes_among_clean_chinese_goes_to_ocr(self):
        garbled = CLEAN * 2 + "ÃäÉöü"
        self.assertTrue(books.readable(garbled))
        self.assertFalse(books.usable(garbled))
        self.assertTrue(books.usable(CLEAN * 2 + "ÃäÉö"), "four odd characters are not yet garbage")

    def test_private_use_bullets_are_not_garbage(self):
        self.assertTrue(books.usable(CLEAN * 2 + ""))


class Resume(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.partial = self.dir / "book.md.partial"

    def markers(self):
        return [line for line in self.partial.read_text(encoding="utf-8").splitlines()
                if line.startswith("=====PAGE")]

    def test_a_torn_last_page_is_cut_and_written_once(self):
        done = books.resume(self.partial)
        for number in (1, 2):
            books.append(self.partial, done, number, "page %d text" % number)
        with self.partial.open("ab") as handle:          # a crash halfway through page 3
            handle.write(books.block(3, "page 3 text").encode("utf-8")[:9])
        done = books.resume(self.partial)
        self.assertEqual(done["pages"], 2)
        books.append(self.partial, done, 3, "page 3 text")
        self.assertEqual(self.markers(), ["=====PAGE 1=====", "=====PAGE 2=====", "=====PAGE 3====="])

    def test_a_partial_without_its_sidecar_starts_over(self):
        self.partial.write_text("=====PAGE 1=====\n\nstale\n\n", encoding="utf-8")
        self.assertEqual(books.resume(self.partial)["pages"], 0)
        self.assertEqual(self.partial.read_bytes(), b"")


class Plan(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        self.library, self.out = root / "library", root / "out"
        (self.library / "a").mkdir(parents=True)
        for key in ("a/one.pdf", "a/two.pdf"):
            (self.library / key).write_bytes(b"%PDF-1.4 " + key.encode())
        self.state = books.load_state(self.out)

    def record(self, key):
        pdf = self.library / key
        stat = pdf.stat()
        self.state["books"][key] = {"size": stat.st_size, "mtime": stat.st_mtime_ns,
                                    "sha256": books.sha256(pdf), "pages": 1, "text_pages": 1,
                                    "ocr_pages": 0, "low_pages": []}
        md = books.target(self.out, key)
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text("x", encoding="utf-8")

    def test_only_a_new_book_is_planned(self):
        self.record("a/one.pdf")
        self.assertEqual(books.plan(self.library, self.out, self.state), (["a/two.pdf"], []))

    def test_a_changed_book_is_planned_and_a_touched_one_is_not(self):
        self.record("a/one.pdf")
        self.record("a/two.pdf")
        os.utime(self.library / "a/one.pdf", ns=(1, 1))            # time moved, bytes did not
        (self.library / "a/two.pdf").write_bytes(b"%PDF-1.4 changed")
        self.assertEqual(books.plan(self.library, self.out, self.state), (["a/two.pdf"], []))

    def test_a_book_removed_upstream_loses_its_markdown(self):
        self.record("a/one.pdf")
        self.record("a/two.pdf")
        (self.library / "a/two.pdf").unlink()
        todo, gone = books.plan(self.library, self.out, self.state)
        self.assertEqual((todo, gone), ([], ["a/two.pdf"]))
        books.forget(self.out, self.state, "a/two.pdf")
        self.assertFalse(books.target(self.out, "a/two.pdf").exists())
        self.assertNotIn("a/two.pdf", self.state["books"])


class Header(unittest.TestCase):
    def test_the_header_names_the_source_and_quotes_the_page_command(self):
        text = books.header("Library/x/Effective Java (2).pdf", "java/Effective Java (2).pdf",
                            303, 0, 303, "RapidOCR 3.9.2 on DirectML", "2026-09-25")
        self.assertTrue(text.startswith("# Effective Java (2)\n\n> **2026-09-25** · books · `current`"))
        self.assertIn('`books page "java/Effective Java (2)" <page>`', text)


launcher = load("books", ROOT / "Library" / "bin" / "books")


class Launcher(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.saved = launcher.run, launcher.PYTHON
        launcher.run = lambda argv: self.calls.append(argv) or 0
        self.addCleanup(self.restore)

    def restore(self):
        launcher.run, launcher.PYTHON = self.saved

    def test_install_makes_the_venv_then_installs_the_pins(self):
        launcher.PYTHON = Path(tempfile.gettempdir()) / "no-such-books-runtime" / "python.exe"
        self.assertEqual(launcher.install(), 0)
        self.assertEqual(self.calls[0][1:3], ["venv", "--python"])
        self.assertEqual(self.calls[1][1:3], ["pip", "install"])
        self.assertEqual(self.calls[1][-2:], ["-r", str(launcher.REQUIREMENTS)])

    def test_engine_commands_run_books_py_in_the_runtime(self):
        launcher.PYTHON = Path(sys.executable)          # a runtime that exists
        self.assertEqual(launcher.main(["status", "--out", "x"]), 0)
        self.assertEqual(self.calls, [[str(Path(sys.executable)), str(launcher.ENGINE), "status", "--out", "x"]])

    def test_only_build_installs_a_missing_runtime(self):
        # status and check only read: they used to download 25 packages first.
        launcher.PYTHON = Path(tempfile.gettempdir()) / "no-such-books-runtime" / "python.exe"
        for command in ("status", "check", "page"):
            with self.subTest(command):
                self.calls.clear()
                self.assertEqual(launcher.main([command]), 1)
                self.assertEqual(self.calls, [])
        launcher.main(["build"])
        self.assertTrue(self.calls and "venv" in self.calls[0], self.calls)

    def test_the_pins_install_directml_only_on_windows(self):
        pins = launcher.REQUIREMENTS.read_text(encoding="utf-8")
        self.assertIn('onnxruntime-directml==1.24.4; sys_platform == "win32"', pins)
        self.assertIn('onnxruntime==1.24.4; sys_platform != "win32"', pins)
        self.assertIn("rapidocr==3.9.2", pins)


RUNTIME = ROOT / "Library" / ".runtime" / "books" / ".venv" / (
    "Scripts/python.exe" if os.name == "nt" else "bin/python")


class FakeText:
    def __init__(self, text):
        self.text = text

    def get_text_range(self):
        return self.text

    def close(self):
        pass


class FakePage:
    def __init__(self, text, broken=False):
        self.text, self.broken = text, broken

    def get_textpage(self):
        if self.broken:
            raise RuntimeError("Failed to load page")
        return FakeText(self.text)

    def render(self, scale):
        return self

    def to_pil(self):
        return "image"

    def close(self):
        pass


class FakeReader:
    name = "fake reader"

    def __call__(self, image):
        return "HELLO 42 read from the image of the page", 0.9

    def working(self):
        return True


class DeadEngine(FakeReader):
    """OCR that has stopped working, as DirectML does when the GPU is lost mid-run."""

    def __call__(self, image):
        raise RuntimeError("DXGI_ERROR_DEVICE_REMOVED")

    def working(self):
        return False


class Convert(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.md = self.dir / "subject" / "book.md"

    def test_each_page_takes_its_route_and_a_broken_page_is_recorded(self):
        doc = [FakePage(CLEAN), FakePage(GLYPH_CODES), FakePage("", broken=True), FakePage(CLEAN)]
        done = books.convert(doc, self.md, FakeReader(), "lib/book.pdf", "subject/book.pdf", "2026-09-25")
        self.assertEqual((done["pages"], done["text_pages"], done["ocr_pages"]), (4, 2, 1))
        self.assertEqual((done["low_pages"], list(done["page_errors"])), ([3], ["3"]))
        text = self.md.read_text(encoding="utf-8")
        self.assertIn("HELLO 42", text.split("=====PAGE 2=====")[1])
        self.assertIn("(fake reader)", text)
        self.assertEqual([int(n) for n in books.MARKER.findall(text)], [1, 2, 3, 4])
        self.assertFalse(self.md.with_name("book.md.partial").exists())

    def test_with_ocr_off_a_scanned_page_is_low_yield(self):
        done = books.convert([FakePage(CLEAN), FakePage("")], self.md, None, "lib/b.pdf", "s/b.pdf", "2026-09-25")
        self.assertEqual(done["low_pages"], [2])

    def test_a_dead_ocr_engine_stops_the_book_at_the_page_it_failed(self):
        doc = [FakePage(CLEAN), FakePage(GLYPH_CODES), FakePage(GLYPH_CODES)]
        with self.assertRaises(RuntimeError):
            books.convert(doc, self.md, DeadEngine(), "lib/book.pdf", "subject/book.pdf", "2026-09-25")
        self.assertFalse(self.md.exists())
        partial = self.md.with_name("book.md.partial")
        self.assertEqual(books.MARKER.findall(partial.read_text(encoding="utf-8")), ["1"])
        self.assertEqual(books.resume(partial)["pages"], 1)


class Rule(unittest.TestCase):
    """A book converted under the old page rule is read again once: only the pages
    the new rule sends to OCR, in place, so no book's OCR is done twice."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def test_only_a_page_the_old_rule_kept_and_the_new_one_sends_to_ocr_flips(self):
        doc = [FakePage(CLEAN), FakePage(SPACED), FakePage(GLYPH_CODES), FakePage("42")]
        self.assertEqual(books.flipped_pages(doc), [2])

    def test_a_flipped_page_is_read_again_in_place_and_the_counts_follow(self):
        md = self.dir / "subject" / "book.md"
        md.parent.mkdir(parents=True)
        md.write_text(books.header("lib/book.pdf", "subject/book.pdf", 3, 3, 0, "fake reader", "2026-09-25")
                      + books.block(1, CLEAN) + books.block(2, SPACED) + books.block(3, CLEAN), encoding="utf-8")
        entry = {"pages": 3, "text_pages": 3, "ocr_pages": 0, "low_pages": [], "page_errors": {},
                 "ocr_confidence": None}
        doc = [FakePage(CLEAN), FakePage(SPACED), FakePage(CLEAN)]
        update = books.repair(doc, md, FakeReader(), [2], entry, "lib/book.pdf", "subject/book.pdf", "2026-09-27")
        text = md.read_text(encoding="utf-8")
        self.assertIn("HELLO 42", text.split("=====PAGE 2=====")[1].split("=====PAGE 3=====")[0])
        self.assertIn(CLEAN, text.split("=====PAGE 2=====")[0])
        self.assertIn(CLEAN, text.split("=====PAGE 3=====")[1])
        self.assertNotIn("T C P", text)
        self.assertEqual([int(n) for n in books.MARKER.findall(text)], [1, 2, 3])
        self.assertIn("2 from the text layer", text)
        self.assertEqual((update["text_pages"], update["ocr_pages"], update["ocr_confidence"]), (2, 1, 0.9))


class Lock(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.out)

    def test_a_live_holder_keeps_the_lock(self):
        (self.out / books.LOCK).write_text(str(os.getppid()), encoding="utf-8")
        self.assertEqual(books.acquire(self.out), os.getppid())

    def test_a_dead_holder_loses_it(self):
        (self.out / books.LOCK).write_text("999999", encoding="utf-8")
        self.assertIsNone(books.acquire(self.out))
        self.assertEqual((self.out / books.LOCK).read_text(encoding="utf-8"), str(os.getpid()))
        books.release(self.out)
        self.assertFalse((self.out / books.LOCK).exists())


class NoLibrary(unittest.TestCase):
    def test_a_device_without_the_library_builds_nothing_and_says_so(self):
        out = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, out)
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            self.assertEqual(books.build(out / "absent", out, None, False), 0)
        self.assertIn("no library", said.getvalue())
        self.assertFalse(books.summary(out / "absent", out)["library"])


def text_pdf(path, line):
    """A one-page PDF whose text layer holds line, in Helvetica; no dependencies."""
    body = "BT /F1 14 Tf 72 720 Td (%s) Tj ET" % line
    objects = ["<< /Type /Catalog /Pages 2 0 R >>",
               "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
               "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               "<< /Length %d >>\nstream\n%s\nendstream" % (len(body), body)]
    out, offsets = "%PDF-1.4\n", []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(out.encode("latin-1")))
        out += "%d 0 obj\n%s\nendobj\n" % (number, obj)
    xref = len(out.encode("latin-1"))
    out += "xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += "".join("%010d 00000 n \n" % offset for offset in offsets)
    out += "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    Path(path).write_bytes(out.encode("latin-1"))


SCAN_PAGE = """
import sys
from PIL import Image, ImageDraw, ImageFont
import pypdfium2 as pdfium
text_pdf, out = sys.argv[1], sys.argv[2]
scan = text_pdf + ".scan.pdf"
image = Image.new("L", (1224, 1584), 255)
ImageDraw.Draw(image).text((150, 600), "HELLO 42", fill=0, font=ImageFont.load_default(size=160))
image.save(scan, "PDF", resolution=144)
book = pdfium.PdfDocument(text_pdf)
book.import_pages(pdfium.PdfDocument(scan))
book.save(out)
"""


def run_books(*args):
    return subprocess.run([sys.executable, str(ROOT / "Library" / "bin" / "books"), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)


# For `python -c`: loads the file named by argv[1] as `module`, for a child that runs one function.
LOADS = """
import importlib.machinery, importlib.util, sys
loader = importlib.machinery.SourceFileLoader("module", sys.argv[1])
module = importlib.util.module_from_spec(importlib.util.spec_from_loader("module", loader))
loader.exec_module(module)
"""


@unittest.skipUnless(RUNTIME.exists(), "no Library/.runtime/books on this device: run books install")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        cls.library, cls.out = cls.root / "library", cls.root / "out"
        (cls.library / "fixture").mkdir(parents=True)
        page_one = cls.root / "page-one.pdf"
        text_pdf(page_one, "The text layer of page one reads cleanly and is kept as it is.")
        subprocess.run([str(RUNTIME), "-c", SCAN_PAGE, str(page_one),
                        str(cls.library / "fixture" / "two-pages.pdf")], check=True)
        for name in ("Effective Java (2).pdf", "中文书.pdf"):
            shutil.copy(page_one, cls.library / "fixture" / name)
        (cls.library / "fixture" / "broken.pdf").write_bytes(b"%\nPDF-1.3 not a document")
        cls.args = ("--library", str(cls.library), "--out", str(cls.out))
        cls.first = run_books("build", *cls.args)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def test_a_second_build_converts_nothing(self):
        self.assertIn("books: 0 converted", run_books("build", *self.args).stdout)

    def test_an_unreadable_pdf_is_listed_and_the_build_goes_on(self):
        state = json.loads((self.out / ".books.json").read_text(encoding="utf-8"))
        self.assertIn("fixture/broken.pdf", state["unreadable"])
        self.assertEqual(len(state["books"]), 3)

    def test_both_routes_land_in_one_book(self):
        self.assertEqual(self.first.returncode, 0, self.first.stdout + self.first.stderr)
        text = (self.out / "fixture" / "two-pages.md").read_text(encoding="utf-8")
        self.assertIn("text layer of page one", text.split("=====PAGE 2=====")[0])
        scanned = text.split("=====PAGE 2=====")[1]
        self.assertIn("HELLO", scanned)
        self.assertIn("42", scanned)

    def test_chinese_and_bracketed_names_convert_and_render(self):
        self.assertIn("fixture/中文书.pdf", self.first.stdout)
        self.assertIn("(<fixture/Effective Java (2).md>)", (self.out / "INDEX.md").read_text(encoding="utf-8"))
        png = self.root / "page.png"
        shown = run_books("page", "fixture/Effective Java (2)", "1", "-o", str(png), "--library", str(self.library))
        self.assertEqual(shown.returncode, 0, shown.stdout)
        self.assertTrue(png.is_file())

    def test_the_engine_check_says_yes_on_a_working_engine(self):
        said = subprocess.run([str(RUNTIME), "-c", LOADS + "print(module.Reader().working())",
                               str(ROOT / "Library" / "books.py")], capture_output=True, text=True, timeout=300)
        # On the Mac, CoreML's native warnings reach stdout after Python's line.
        verdicts = [line.strip() for line in said.stdout.splitlines() if line.strip() in ("True", "False")]
        self.assertEqual(verdicts, ["True"], said.stderr[-2000:])

    def test_status_and_check_pass_then_catch_a_broken_output(self):
        self.assertEqual(run_books("status", *self.args).returncode, 0)
        self.assertEqual(run_books("check", "--full", *self.args).returncode, 0)
        md = self.out / "fixture" / "two-pages.md"
        saved = md.read_text(encoding="utf-8")
        try:
            md.write_text(saved.split("=====PAGE 2=====")[0], encoding="utf-8")
            self.assertEqual(run_books("check", "--full", *self.args).returncode, 1)
            md.unlink()
            self.assertEqual(run_books("status", *self.args).returncode, 1)
        finally:
            md.write_text(saved, encoding="utf-8")


@unittest.skipUnless(RUNTIME.exists(), "no Library/.runtime/books on this device: run books install")
class RuleUpgrade(unittest.TestCase):
    """The page rule changed on 2026-09-27; every device's next build carries it out."""

    def test_a_book_from_the_old_rule_has_its_flipped_page_read_again(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        library, out = root / "library", root / "out"
        (library / "fixture").mkdir(parents=True)
        spaced_line = "Our T C P / I P stack speaks I n t e r n e t over 1 0 0 links of the network here."
        text_pdf(library / "fixture" / "spaced.pdf", spaced_line)
        args = ("--library", str(library), "--out", str(out))
        first = run_books("build", *args)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        md, state_file = out / "fixture" / "spaced.md", out / ".books.json"
        self.assertIn("0 from the text layer", md.read_text(encoding="utf-8"), "the new rule sends it to OCR at once")
        # Stage the book as the old rule left it: its page from the text layer, no rule in the state.
        state = json.loads(state_file.read_text(encoding="utf-8"))
        entry = state["books"]["fixture/spaced.pdf"]
        self.assertEqual(entry.pop("rule"), books.RULE)
        entry.update(text_pages=1, ocr_pages=0)
        state_file.write_text(json.dumps(state), encoding="utf-8")
        head = books.header("x", "fixture/spaced.pdf", 1, 1, 0, "RapidOCR", "2026-09-25")
        md.write_text(head + books.block(1, spaced_line), encoding="utf-8")
        second = run_books("build", *args)
        self.assertIn("repaired fixture/spaced.pdf", second.stdout, second.stdout + second.stderr)
        self.assertIn("0 from the text layer", md.read_text(encoding="utf-8"))
        entry = json.loads(state_file.read_text(encoding="utf-8"))["books"]["fixture/spaced.pdf"]
        self.assertEqual((entry["rule"], entry["text_pages"], entry["ocr_pages"]), (books.RULE, 0, 1))
        third = run_books("build", *args)
        self.assertIn("books: 0 converted, 0 repaired", third.stdout)
        self.assertNotIn("repaired fixture/", third.stdout)


class Start(unittest.TestCase):
    def test_start_returns_at_once_and_spawns_a_build(self):
        calls = []

        class FakePopen:
            def __init__(self, argv, **kwargs):
                calls.append(argv)

        saved = launcher.subprocess.Popen, launcher.LOG
        launcher.subprocess.Popen = FakePopen
        launcher.LOG = Path(tempfile.mkdtemp()) / "books.log"
        try:
            began = time.monotonic()
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                self.assertEqual(launcher.main(["start", "--library", "x", "--out", "y"]), 0)
            self.assertIn("started a detached build", said.getvalue())
        finally:
            shutil.rmtree(launcher.LOG.parent)
            launcher.subprocess.Popen, launcher.LOG = saved
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual(calls[0][2:], ["build", "--library", "x", "--out", "y"])

    @unittest.skipUnless(os.name == "nt", "Task Scheduler is Windows'")
    def test_start_registers_a_missing_task_then_runs_it_windowless(self):
        calls, registered = [], []

        def schtasks(argv, **kwargs):
            calls.append((argv[1], kwargs.get("creationflags")))
            return subprocess.CompletedProcess(argv, 1 if argv[1] == "/Query" else 0)

        saved = launcher.subprocess.run, launcher.subprocess.Popen, launcher.schedule, launcher.LOG
        launcher.subprocess.run = schtasks
        launcher.subprocess.Popen = lambda argv, **kwargs: calls.append(("a detached build", None))
        launcher.schedule = lambda install_task: registered.append(install_task) or 0
        launcher.LOG = Path(tempfile.mkdtemp()) / "books.log"
        try:
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                self.assertEqual(launcher.main(["start"]), 0)
        finally:
            shutil.rmtree(launcher.LOG.parent)
            launcher.subprocess.run, launcher.subprocess.Popen, launcher.schedule, launcher.LOG = saved
        self.assertEqual(registered, [True])
        self.assertEqual(calls, [("/Query", launcher.NO_WINDOW), ("/Run", launcher.NO_WINDOW)])
        self.assertIn("started DEVARNESS_books_build", said.getvalue())


@unittest.skipUnless(os.name == "nt", "consoles and jobs are Windows'")
class Run(unittest.TestCase):
    """The launcher's child when nothing has a console: a detached start, or update-tools's pythonw."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def launcher_running(self, child, **options):
        """A launcher process whose run() starts `python -c child`."""
        return subprocess.Popen([sys.executable, "-c", LOADS + "sys.exit(module.run(sys.argv[2:]))",
                                 str(ROOT / "Library" / "bin" / "books"), sys.executable, "-c", child], **options)

    def test_a_detached_build_logs_its_output_and_shows_no_window(self):
        log = self.dir / "build.log"
        child = ("import ctypes; k = ctypes.windll; "
                 "print('window shown:', k.user32.IsWindowVisible(k.kernel32.GetConsoleWindow()))")
        with log.open("w") as out:
            self.launcher_running(child, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                                  creationflags=subprocess.DETACHED_PROCESS).wait(timeout=60)
        self.assertIn("window shown: 0", log.read_text(encoding="utf-8"))

    def test_the_build_ends_with_its_launcher(self):
        pid_file = self.dir / "build.pid"
        child = "import os, pathlib, time; pathlib.Path(%r).write_text(str(os.getpid())); time.sleep(120)" % str(
            pid_file)
        running = self.launcher_running(child, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while not (pid_file.exists() and pid_file.read_text().strip()) and time.monotonic() < deadline:
            time.sleep(0.1)
        pid = int(pid_file.read_text())
        self.addCleanup(subprocess.run, ["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        running.kill()                  # all that Task Scheduler's End does, by the 2026-09-25 probe
        running.wait(timeout=30)
        deadline = time.monotonic() + 10
        while books.pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertFalse(books.pid_alive(pid))


class Wiring(unittest.TestCase):
    def test_the_text_and_the_log_are_never_tracked(self):
        for path in ("Books/text/any/book.md", ".claude/hooks/books.log"):
            done = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", path])
            self.assertEqual(done.returncode, 0, path)

    def test_the_preflight_names_books(self):
        update = load("update_tools", ROOT / "Library" / "bin" / "update-tools")
        done = subprocess.run([update.bash_path(), str(ROOT / ".claude" / "hooks" / "preflight.sh")],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120, cwd=str(ROOT),
                              env=dict(os.environ, DEVARNESS_START_ALL="1"))  # a healthy banner lists no rows
        self.assertIn("books", json.loads(done.stdout)["systemMessage"])

    def test_bootstrap_links_books(self):
        self.assertIn(" books", (ROOT / "Library" / "bootstrap.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
