"""Installer regressions using disposable files, without downloads or a build.

Run: python3 -m unittest discover -s Library/tests -p 'test_ngspice_setup.py' -v
The live ngspice operating-point test remains ngspice-setup --check.
"""

from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "ngspice-setup"


class NgspiceSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ngspice setup test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        module = runpy.run_path(str(SCRIPT))
        self.setup = module["install"].__globals__
        self.prefix = self.root / "runtime" / "ngspice" / self.setup["VERSION"]
        self.setup["PREFIX"] = self.prefix
        self.lock = self.prefix.parent / ("." + self.setup["VERSION"] + ".install.lock")
        # These cover the macOS source build and its link, whatever the host.
        darwin = patch("platform.system", return_value="Darwin")
        darwin.start()
        self.addCleanup(darwin.stop)

    def fake_compiler_availability(self, stack):
        # Host/tool discovery is outside the filesystem behavior under test.
        stack.enter_context(patch("platform.system", return_value="Darwin"))
        stack.enter_context(patch("shutil.which", return_value="fixture compiler"))

    def fixture_archive(self):
        archive = self.root / "source.tar.gz"
        source_name = "ngspice-" + self.setup["VERSION"]
        with tarfile.open(archive, "w:gz") as package:
            directory = tarfile.TarInfo(source_name)
            directory.type = tarfile.DIRTYPE
            directory.mode = 0o755
            package.addfile(directory)
            body = b"# Compilation is replaced at the subprocess boundary.\n"
            configure = tarfile.TarInfo(source_name + "/configure")
            configure.size = len(body)
            configure.mode = 0o755
            package.addfile(configure, io.BytesIO(body))
        # This changes only the imported test instance, never the production pin.
        self.setup["SHA256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        return archive

    def test_missing_check_is_read_only(self):
        # Catches false readiness and writes during the real --check command.
        script = self.root / "Library" / "bin" / SCRIPT.name
        script.parent.mkdir(parents=True)
        script.write_bytes(SCRIPT.read_bytes())
        result = subprocess.run([sys.executable, str(script), "--check"],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "missing")
        self.assertFalse((self.root / "Library" / ".runtime").exists())

    def test_corrupt_archive_is_rejected_before_extraction(self):
        # Catches accepting a changed archive or executing its contents.
        archive = self.fixture_archive()
        archive.write_bytes(b"changed source must never be extracted or executed")
        with ExitStack() as stack:
            self.fake_compiler_availability(stack)
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                self.setup["install"](str(archive))
        self.assertFalse(self.prefix.exists())
        self.assertFalse(self.lock.exists())

    @unittest.skipIf(os.name == "nt", "the source build stages under a POSIX absolute prefix")
    def test_publication_race_preserves_competing_runtime(self):
        # Reproduces a writer appearing after lexists: shutil.move previously
        # nested the staged runtime and replaced the other writer's metadata.
        archive = self.fixture_archive()
        real_lexists = os.path.lexists
        staged = False
        raced = False

        def racing_lexists(path):
            nonlocal raced
            exists = real_lexists(path)
            if Path(path) == self.prefix and staged and not exists:
                raced = True
                (self.prefix / "bin").mkdir(parents=True)
                (self.prefix / "bin" / "ngspice").write_text("competitor binary")
                (self.prefix / "build.log").write_text("competitor log")
                (self.prefix / "install.json").write_text("competitor metadata")
                return False  # It appeared immediately after the actual check.
            return exists

        def compiler_run(command, **kwargs):
            nonlocal staged
            if command == ["xcrun", "--show-sdk-path"]:
                return subprocess.CompletedProcess(command, 0, stdout=str(self.root / "sdk") + "\n")
            if command[0] == "clang++":
                return subprocess.CompletedProcess(command, 0)
            if command[0] == "make":
                if command[1] == "install":
                    stage = Path(command[2].split("=", 1)[1])
                    destination = stage / str(self.prefix).lstrip(os.sep)
                    (destination / "bin").mkdir(parents=True)
                    (destination / "bin" / "ngspice").write_text("new binary")
                    staged = True
                return subprocess.CompletedProcess(command, 0)
            if Path(command[0]).name == "configure" and Path(command[0]).is_file():
                return subprocess.CompletedProcess(command, 0)
            raise AssertionError("Unexpected external command: " + repr(command))

        with ExitStack() as stack:
            self.fake_compiler_availability(stack)
            stack.enter_context(patch("os.path.lexists", racing_lexists))
            stack.enter_context(patch("subprocess.run", compiler_run))
            stack.enter_context(patch.dict(self.setup, {"probe": lambda binary: {"status": "ready"}}))
            stack.enter_context(patch.object(Path, "home", return_value=self.root / "home"))
            with self.assertRaisesRegex(RuntimeError, "publication"):
                self.setup["install"](str(archive))
        self.assertTrue(raced, "The race must reach the real publication path")
        self.assertEqual((self.prefix / "bin" / "ngspice").read_text(), "competitor binary")
        self.assertEqual((self.prefix / "build.log").read_text(), "competitor log")
        self.assertEqual((self.prefix / "install.json").read_text(), "competitor metadata")
        self.assertFalse((self.prefix / self.setup["VERSION"]).exists())
        self.assertFalse(self.lock.exists())
        self.assertFalse((self.root / "home").exists())

    def test_existing_lock_is_refused_and_preserved(self):
        # Catches a second installer entering or removing another owner's lock.
        self.lock.mkdir(parents=True)
        owner = self.lock / "owner.json"
        owner.write_text("existing owner")
        with self.assertRaisesRegex(RuntimeError, "Install lock exists"):
            self.setup["install"](None)
        self.assertEqual(owner.read_text(), "existing owner")
        self.assertFalse(self.prefix.exists())

    def test_incomplete_runtime_is_refused_and_preserved(self):
        # A binary alone, or a pending marker beside valid metadata, is not ready.
        binary = self.prefix / "bin" / "ngspice"
        binary.parent.mkdir(parents=True)
        binary.write_text("partial binary")
        for state in ("no installation record", "pending publication"):
            with self.subTest(state=state):
                if state == "pending publication":
                    record = {"version": self.setup["VERSION"], "source_sha256": self.setup["SHA256"]}
                    (self.prefix / "install.json").write_text(json.dumps(record))
                    (self.prefix / ".installing").write_text("pending owner")
                with self.assertRaisesRegex(RuntimeError, "incomplete or unmanaged"):
                    self.setup["install"](None)
                self.assertEqual(binary.read_text(), "partial binary")
                self.assertFalse(self.lock.exists())

    def test_link_creation_is_idempotent(self):
        # Catches failing to expose the runtime or replacing the existing link.
        binary = self.root / "runtime-binary"
        binary.write_text("runtime fixture")
        link = self.root / ".local" / "bin" / "ngspice"
        with patch.object(Path, "home", return_value=self.root):
            self.setup["add_link"](binary)
            original = link.lstat()
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), binary)
            self.setup["add_link"](binary)
        self.assertEqual(link.lstat().st_ino, original.st_ino)
        self.assertEqual(link.resolve(), binary)

    def test_existing_file_and_dangling_link_are_preserved(self):
        # Catches overwriting an owner's binary or a temporarily dangling link.
        binary = self.root / "new-binary"
        binary.write_text("new binary")
        link = self.root / ".local" / "bin" / "ngspice"
        link.parent.mkdir(parents=True)
        with patch.object(Path, "home", return_value=self.root):
            link.write_text("owner binary")
            self.setup["add_link"](binary)
            self.assertFalse(link.is_symlink())
            self.assertEqual(link.read_text(), "owner binary")
            link.unlink()
            unavailable = self.root / "unavailable"
            link.symlink_to(unavailable)
            self.setup["add_link"](binary)
            self.assertTrue(link.is_symlink())
            self.assertFalse(link.exists())
            self.assertEqual(link.resolve(), unavailable)


class WindowsInstallTests(unittest.TestCase):
    """The prebuilt Windows install, with fixtures at the network and 7zr boundaries."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ngspice windows test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        module = runpy.run_path(str(SCRIPT))
        self.setup = module["install"].__globals__
        self.prefix = self.root / "runtime" / "ngspice" / self.setup["VERSION"]
        self.setup["PREFIX"] = self.prefix
        self.home = self.root / "home"
        self.archive = self.root / "fixture.7z"
        self.archive.write_bytes(b"fixture prebuilt archive")
        self.unpacker = self.root / "fixture-7zr.exe"
        self.unpacker.write_bytes(b"fixture unpacker")
        # Changes only this imported instance, never the production pins.
        self.setup["WINDOWS_SHA256"] = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.setup["SEVENZR_SHA256"] = hashlib.sha256(self.unpacker.read_bytes()).hexdigest()
        self.fetched = []
        self.unpacked = []

    def fetch(self, url, destination):
        self.fetched.append(url)
        source = self.unpacker if url == self.setup["SEVENZR_URL"] else self.archive
        shutil.copyfile(str(source), str(destination))

    def unpack(self, command, **kwargs):
        self.unpacked.append(command)
        stage = Path(command[3][2:])
        (stage / "Spice64" / "bin").mkdir(parents=True)
        (stage / "Spice64" / "bin" / "ngspice_con.exe").write_bytes(b"console build")
        (stage / "Spice64" / "bin" / "ngspice.exe").write_bytes(b"windowed build")
        return subprocess.CompletedProcess(command, 0)

    def install(self, unpack=None):
        with ExitStack() as stack:
            stack.enter_context(patch("platform.system", return_value="Windows"))
            stack.enter_context(patch("subprocess.run", unpack or self.unpack))
            stack.enter_context(patch.object(Path, "home", return_value=self.home))
            ready = {"status": "ready", "version": self.setup["VERSION"],
                     "source_sha256": self.setup["WINDOWS_SHA256"]}
            stack.enter_context(patch.dict(self.setup, {"fetch": self.fetch,
                                                        "probe": lambda binary: dict(ready)}))
            return self.setup["install"](None)

    def test_the_console_build_is_installed_with_a_command_for_it(self):
        report = self.install()
        binary = self.prefix / "Spice64" / "bin" / "ngspice_con.exe"
        self.assertEqual(binary.read_bytes(), b"console build")
        self.assertEqual(self.fetched, [self.setup["WINDOWS_URL"], self.setup["SEVENZR_URL"]])
        self.assertTrue((self.prefix / "install.json").is_file())
        self.assertFalse((self.prefix / ".installing").exists())
        command = self.home / ".local" / "bin" / "ngspice.cmd"
        self.assertEqual(command.read_bytes(), ('@"' + str(binary) + '" %*\r\n').encode("utf-8"))
        self.assertTrue(report["link"].startswith("created"))

    def test_a_changed_archive_is_rejected_before_anything_is_unpacked(self):
        self.setup["WINDOWS_SHA256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "prebuilt archive rejected"):
            self.install()
        self.assertEqual(self.unpacked, [])
        self.assertFalse(self.prefix.exists())

    def test_a_changed_unpacker_is_never_run(self):
        self.setup["SEVENZR_SHA256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "7zr.exe rejected"):
            self.install()
        self.assertEqual(self.unpacked, [])
        self.assertFalse(self.prefix.exists())

    def test_an_existing_ngspice_command_is_preserved(self):
        existing = self.home / ".local" / "bin" / "ngspice.exe"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"owner build")
        report = self.install()
        self.assertEqual(existing.read_bytes(), b"owner build")
        self.assertFalse((existing.parent / "ngspice.cmd").exists())
        self.assertIn("preserved", report["link"])

    def test_a_path_cmd_would_misread_gets_no_command(self):
        # cmd.exe expands %NAME% and reads a .cmd file in the console code
        # page, so such a shim ran nothing, and --check could not tell
        # (review of the phase 4 diff, minor finding 4).
        for folder in ("C:/tools/100%/Spice64/bin", "C:/tools/caf\u00e9/Spice64/bin"):
            with self.subTest(folder=folder), patch.object(Path, "home", return_value=self.home):
                report = self.setup["add_command"](Path(folder) / "ngspice_con.exe")
                self.assertIn("cannot", report)
                self.assertFalse((self.home / ".local" / "bin" / "ngspice.cmd").exists())

    def test_check_reports_whether_the_command_still_starts_this_runtime(self):
        binary = self.prefix / "Spice64" / "bin" / "ngspice_con.exe"
        command = self.home / ".local" / "bin" / "ngspice.cmd"
        with patch.object(Path, "home", return_value=self.home):
            self.assertEqual(self.setup["command_state"](binary), "absent")
            self.setup["add_command"](binary)
            self.assertEqual(self.setup["command_state"](binary), "starts this runtime")
            command.write_bytes(b'@"D:\\old\\ngspice_con.exe" %*\r\n')
            self.assertIn("another", self.setup["command_state"](binary))

    def test_installing_a_second_time_leaves_the_same_command(self):
        self.install()
        command = self.home / ".local" / "bin" / "ngspice.cmd"
        body, stamp = command.read_bytes(), command.stat().st_mtime_ns
        with patch.object(Path, "home", return_value=self.home):
            again = self.setup["add_command"](self.prefix / "Spice64" / "bin" / "ngspice_con.exe")
        self.assertEqual(again, "already linked")
        self.assertEqual((command.read_bytes(), command.stat().st_mtime_ns), (body, stamp))

    def test_an_unpacker_that_fails_is_reported_with_what_it_said(self):
        # Its output was captured and thrown away, so the reason never showed.
        def failing(command, **kwargs):
            self.unpacked.append(command)
            return subprocess.CompletedProcess(command, 2, stdout="ERROR: CRC failed", stderr="")
        with self.assertRaisesRegex(RuntimeError, "CRC failed"):
            self.install(failing)
        self.assertFalse(self.prefix.exists())

    def test_a_download_that_fails_once_is_tried_again(self):
        # The macOS path passes curl --retry 2; this one gave up at the first error.
        attempts = []

        class Response(io.BytesIO):
            def geturl(self):
                return "https://downloads.example/ngspice.7z"

        class Opener:
            def open(self, request, timeout):
                attempts.append(request.full_url)
                if len(attempts) == 1:
                    raise OSError("connection reset")
                return Response(b"payload")
        destination = self.root / "retried"
        with patch("urllib.request.build_opener", return_value=Opener()), \
                patch.object(self.setup["time"], "sleep", lambda seconds: None):
            self.setup["fetch"]("https://downloads.example/ngspice.7z", destination)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(destination.read_bytes(), b"payload")

    def test_a_redirect_away_from_https_is_refused_before_it_is_followed(self):
        # Only the final address was checked; a hop through plain HTTP was
        # followed (review of the phase 4 diff, minor finding 5).
        import urllib.request
        handler = self.setup["HttpsOnly"]()
        request = urllib.request.Request("https://downloads.example/ngspice.7z")
        with self.assertRaisesRegex(RuntimeError, "left HTTPS"):
            handler.redirect_request(request, None, 302, "Found", {}, "http://mirror.example/ngspice.7z")

    def test_a_download_past_its_limit_is_refused(self):
        class Response(io.BytesIO):
            def geturl(self):
                return "https://downloads.example/ngspice.7z"

        class Opener:
            def open(self, request, timeout):
                return Response(b"x" * 64)
        destination = self.root / "download"
        with patch("urllib.request.build_opener", return_value=Opener()), \
                self.assertRaisesRegex(RuntimeError, "limit"):
            self.setup["fetch"]("https://downloads.example/ngspice.7z", destination, limit=16)

    @unittest.skipUnless(os.name == "nt", "junctions")
    def test_an_unpacked_junction_is_refused_and_nothing_is_published(self):
        import _winapi
        outside = self.root / "outside"
        outside.mkdir()

        def unpack_with_a_junction(command, **kwargs):
            self.unpack(command)
            _winapi.CreateJunction(str(outside), str(Path(command[3][2:]) / "Spice64" / "escape"))
            return subprocess.CompletedProcess(command, 0)
        with self.assertRaisesRegex(RuntimeError, "Unsafe archive entry"):
            self.install(unpack_with_a_junction)
        self.assertFalse(self.prefix.exists())
        self.assertTrue(outside.is_dir(), "cleanup must not follow the junction")


if __name__ == "__main__":
    unittest.main()
