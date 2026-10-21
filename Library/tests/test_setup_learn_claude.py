"""Boundary tests for the pinned course installer, without network or model calls."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "learn_setup", Path(__file__).resolve().parents[1] / "setup-learn-claude.py")
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


class InstallerBoundaries(unittest.TestCase):
    def test_non_posix_reports_course_platform_limit(self):
        with patch.object(SETUP.os, "name", "nt"):
            with self.assertRaisesRegex(RuntimeError, "upstream imports fcntl"):
                SETUP.locations()

    def test_install_and_check_are_not_applicable_off_posix(self):
        # update-tools runs --install after each move; failing there marked the tool
        # stuck and every Windows session DEGRADED (2026-09-28 to 2026-10-02).
        with patch.object(SETUP.os, "name", "nt"), patch("sys.stdout", new=io.StringIO()) as out:
            self.assertEqual(SETUP.main(["--install"]), 0)
            self.assertEqual(SETUP.main(["--check"]), 0)
        self.assertIn('"applicable": false', out.getvalue())

    def test_manifest_refuses_missing_duplicate_or_unreviewed_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "repos.txt"
            row = "Library/learn-claude-code\t" + SETUP.URL + "\t" + SETUP.PIN + "\n"
            for content in ("", row + row, row.replace(SETUP.PIN, "0" * 40)):
                manifest.write_text(content)
                with self.assertRaises(RuntimeError):
                    SETUP.manifest_pin(root)
            manifest.write_text(row)
            self.assertEqual(SETUP.manifest_pin(root), SETUP.PIN)

    def test_archive_rejects_traversal_and_links_before_any_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, kind in (("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
                               ("link", tarfile.SYMTYPE), ("hardlink", tarfile.LNKTYPE)):
                archive = root / "source.tar"
                with tarfile.open(archive, "w") as handle:
                    good = tarfile.TarInfo("good")
                    good.size = 4
                    handle.addfile(good, io.BytesIO(b"good"))
                    bad = tarfile.TarInfo(name)
                    bad.type = kind
                    bad.linkname = "../escape"
                    handle.addfile(bad)
                destination = root / "output"
                with self.assertRaises(RuntimeError):
                    SETUP.extract_archive(archive, destination)
                self.assertFalse(destination.exists())

    def test_copy_hash_check_detects_mutation_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b"teaching source\n"
            (root / "code.py").write_bytes(payload)
            digest = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
            tree = "100644 blob " + digest + "\tcode.py\0"
            with patch.object(SETUP, "run", return_value=subprocess.CompletedProcess([], 0, tree)):
                before = (root / "code.py").stat().st_mtime_ns
                self.assertEqual(SETUP.verify_copy(root, root), 1)
                self.assertEqual(before, (root / "code.py").stat().st_mtime_ns)
                (root / "code.py").write_bytes(b"changed")
                with self.assertRaisesRegex(RuntimeError, "differs from the pin"):
                    SETUP.verify_copy(root, root)

    def test_verification_environment_drops_real_credentials_and_startup_hooks(self):
        with patch.dict(SETUP.os.environ, {"ANTHROPIC_API_KEY": "t" + "est-secret-must-not-propagate",
                                         "AWS_SECRET_ACCESS_KEY": "test-secret",
                                         "PYTHONSTARTUP": "untrusted.py", "PYTHONPATH": "untrusted"}):
            env = SETUP.offline_environment(Path("guard"), Path("venv/bin/python"))
        self.assertEqual(env["ANTHROPIC_API_KEY"], "offline-dummy")
        self.assertEqual(env["PYTHONPATH"], "guard")
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", env)
        self.assertNotIn("PYTHONSTARTUP", env)
        self.assertEqual(env["PYTHON_DOTENV_DISABLED"], "1")
        self.assertTrue(env["PATH"].startswith(str(Path("venv/bin"))))
        self.assertEqual(env["PYTHONUTF8"], "0")

    @unittest.skipIf(os.name == "nt", "install refuses Windows before the lock; the platform test covers that")
    def test_existing_install_lock_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "repos.txt").write_text("Library/learn-claude-code\t" + SETUP.URL + "\t" + SETUP.PIN + "\n")
            parent = root / ".runtime" / SETUP.REPO
            parent.mkdir(parents=True)
            lock = parent / (SETUP.PIN + ".install.lock")
            lock.mkdir()
            with patch.object(SETUP, "verify_clone"), patch.object(SETUP.shutil, "which", return_value="uv"):
                with self.assertRaisesRegex(RuntimeError, "installation lock exists"):
                    SETUP.install(root)
            self.assertTrue(lock.is_dir())


if __name__ == "__main__":
    unittest.main()
