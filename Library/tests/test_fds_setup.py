"""FDS installer regressions using disposable files, without a download.

Run: python3 -m unittest discover -s Library/tests -p 'test_fds_setup.py' -v
The live proof that FDS computes a fire remains fds-setup --check.
"""

import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "fds-setup"


def tar_bytes(entries):
    """entries: (name, kind, payload) where kind is file, dir or symlink."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as package:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            if kind == "dir":
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                package.addfile(info)
            elif kind == "symlink":
                info.type, info.linkname = tarfile.SYMTYPE, payload
                package.addfile(info)
            else:
                body = payload.encode()
                info.size, info.mode = len(body), 0o755
                package.addfile(info, io.BytesIO(body))
    return buffer.getvalue()


FDS_OK = "#!/bin/sh\necho 'STOP: FDS completed successfully (CHID: probe)'\n"
FDS_SILENT = "#!/bin/sh\necho 'ERROR: something else happened'\nexit 0\n"
GOOD_TREE = [
    (".", "dir", None),
    ("./bin", "dir", None),
    ("./bin/fds", "file", FDS_OK),
    ("./bin/openmpi_64", "dir", None),
    ("./bin/openmpi_64/bin", "dir", None),
    ("./bin/openmpi_64/bin/orterun", "file", "#!/bin/sh\n"),
    ("./bin/openmpi_64/bin/mpiexec", "symlink", "orterun"),
    ("./smvbin", "dir", None),
    ("./smvbin/smokeview", "file", "#!/bin/sh\n"),
]


class FdsSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fds setup test ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.setup = runpy.run_path(str(SCRIPT))
        self.prefix = self.root / "runtime with spaces" / "fds" / self.setup["VERSION"]
        self.links = self.root / "home" / ".local" / "bin"

    def installer(self, entries=GOOD_TREE):
        path = self.root / "FDS_osx.sh"
        path.write_bytes(b"#!/bin/bash\necho 'NIST header'\nexit 0\n"
                         b"__TARFILE_FOLLOWS__\n" + tar_bytes(entries))
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_wrong_hash_is_refused_and_leaves_no_prefix(self):
        path, _ = self.installer()
        with self.assertRaisesRegex(RuntimeError, "SHA-256"):
            self.setup["extract"](path, self.prefix, "0" * 64)
        self.assertFalse(os.path.lexists(self.prefix))

    def test_extract_publishes_fds_and_smokeview_and_records_the_pin(self):
        path, digest = self.installer()
        self.setup["extract"](path, self.prefix, digest)
        self.assertTrue((self.prefix / "bin" / "fds").is_file())
        self.assertTrue((self.prefix / "smvbin" / "smokeview").is_file())
        self.assertEqual(os.readlink(self.prefix / "bin/openmpi_64/bin/mpiexec"), "orterun")
        record = json.loads((self.prefix / "install.json").read_text())
        self.assertEqual((record["version"], record["installer_sha256"]),
                         (self.setup["VERSION"], digest))
        self.assertEqual([p.name for p in self.prefix.parent.iterdir()], [self.prefix.name])

    def test_member_escaping_the_prefix_is_refused(self):
        for bad in ([("./bin/fds", "symlink", "../../../../etc/passwd")],
                    [("../outside", "file", "x")]):
            with self.subTest(bad=bad):
                path, digest = self.installer(GOOD_TREE[:2] + bad)
                with self.assertRaisesRegex(RuntimeError, "Unsafe"):
                    self.setup["extract"](path, self.prefix, digest)
                self.assertFalse(os.path.lexists(self.prefix))

    def test_existing_prefix_is_preserved(self):
        self.prefix.mkdir(parents=True)
        (self.prefix / "keep.txt").write_text("owner data")
        path, digest = self.installer()
        with self.assertRaisesRegex(RuntimeError, "exists"):
            self.setup["extract"](path, self.prefix, digest)
        self.assertEqual((self.prefix / "keep.txt").read_text(), "owner data")

    def test_wrapper_never_overwrites_a_foreign_file_but_refreshes_its_own(self):
        write = self.setup["write_wrapper"]
        text = self.setup["wrapper_text"](self.prefix, "bin/fds")
        self.assertEqual(write(self.links, "fds", text), "created")
        self.assertIn(str(self.prefix), (self.links / "fds").read_text())
        self.assertTrue(os.access(self.links / "fds", os.X_OK))
        self.assertEqual(write(self.links, "fds", text + "\n"), "refreshed")
        (self.links / "smokeview").write_text("someone else's smokeview")
        self.assertIn("preserved", write(self.links, "smokeview", text))
        self.assertEqual((self.links / "smokeview").read_text(), "someone else's smokeview")

    @unittest.skipIf(os.name == "nt", "the probe runs NIST's macOS build from /tmp; on Windows FDS comes with PyroSim")
    def test_check_requires_the_success_line(self):
        for body, passes in ((FDS_OK, True), (FDS_SILENT, False)):
            with self.subTest(passes=passes):
                tree = [e if e[0] != "./bin/fds" else ("./bin/fds", "file", body) for e in GOOD_TREE]
                prefix = self.prefix.parent / ("case-" + str(passes))
                path, digest = self.installer(tree)
                self.setup["extract"](path, prefix, digest)
                if passes:
                    report = self.setup["check"](prefix, digest)
                    self.assertEqual(report["status"], "ready")
                else:
                    with self.assertRaisesRegex(RuntimeError, "did not complete"):
                        self.setup["check"](prefix, digest)

    def test_check_refuses_an_unmanaged_prefix(self):
        (self.prefix / "bin").mkdir(parents=True)
        (self.prefix / "bin" / "fds").write_text(FDS_OK)
        with self.assertRaisesRegex(RuntimeError, "unmanaged"):
            self.setup["check"](self.prefix, self.setup["SHA256"])


if __name__ == "__main__":
    unittest.main()
