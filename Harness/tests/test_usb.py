"""The USB payload: pack.sh makes it, verify checks it, install.sh puts dev on a machine from it.

Run: python3 Harness/tests/test_usb.py

A small dev repository is committed with the real bootstrap.sh, the stand-ins
of test_bootstrap_clone and a two-archive reverse-tool manifest, beside three
pinned clones: a full one, packed as a bundle; a shallow one with a token in
its git config, packed as a tar of its .git with the token left behind; and a
local copy of a blobless one. The books clone and Books/text live in a folder
of their own, and the two archives in per-tool folders, as they were
downloaded. pack.sh packs it once, install.sh installs it with --no-system into
a fake home, and the result is checked. No network, real home or scheduled
task is involved.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import unittest

from test_bootstrap_clone import BASH, SETTINGS, TRIPWIRES, URL, Workspace, digest, git, is_dir_link, write

SOURCE = Path(__file__).resolve().parents[2]
PACK = SOURCE / "Harness" / "usb" / "pack.sh"
ROWS = ("Harness/tool", "Harness/thin", "Harness/lazy")
BOOKS = "Harness/pdfs"       # a personal row, in the owner's config, never in git
TOKEN = "tok3n-not-for-the-usb"
ARCHIVES = {"jdk": ("jdk/jdk-21.zip", b"a jdk\n"), "apktool": ("apktool/apktool.jar", b"a jar\n")}


def python3_is_312():
    if not BASH:
        return False
    found = subprocess.run([BASH, "-c", "python3 -c 'import sys; print(sys.version_info[:2])'"],
                           capture_output=True, text=True)
    return found.stdout.strip() == "(3, 12)"


@unittest.skipUnless(BASH, "bash is required")
class UsbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ws = cls.ws = Workspace(cls.addClassCleanup, rows=ROWS)
        dev = ws.dev
        write(dev / ".gitignore", "/Harness/tool/\n/Harness/thin/\n/Harness/lazy/\n/Harness/pdfs/\n"
                                  "/Harness/.runtime/\n*.partial/\n/Books/text/\n")
        cls.downloads = ws.root / "downloads"
        tools = {}
        for tool, (rel, data) in ARCHIVES.items():
            (cls.downloads / rel).parent.mkdir(parents=True, exist_ok=True)
            (cls.downloads / rel).write_bytes(data)
            tools[tool] = {"file": Path(rel).name, "sha256": hashlib.sha256(data).hexdigest()}
        write(dev / "Harness" / "setup" / "reverse-downloads.json", json.dumps({"tools": tools}, indent=2))
        git("init", "-q", str(dev))
        for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.invalid"),
                           ("core.autocrlf", "false")):
            git("config", key, value, cwd=dev)
        git("add", "-A", cwd=dev)
        git("commit", "-q", "-m", "dev", cwd=dev)
        git("clone", "-q", str(ws.upstream), str(dev / "Harness" / "tool"))
        git("checkout", "-q", ws.pin, cwd=dev / "Harness" / "tool")
        thin = dev / "Harness" / "thin"
        git("clone", "-q", "--depth", "1", "--branch", "pin", ws.upstream.as_uri(), str(thin))
        git("config", "http.extraheader", "AUTHORIZATION: basic " + TOKEN, cwd=thin)
        git("remote", "set-url", "origin", "https" + "://user:%s@example.invalid/thin.git" % TOKEN, cwd=thin)
        # A local clone of a blobless clone, as dev-build's were made: its .promisor
        # packs came along, the promisor setting did not, and the tip's blob is missing.
        git("config", "uploadpack.allowfilter", "true", cwd=ws.upstream)
        blobless = ws.root / "blobless"
        git("clone", "-q", "--filter=blob:none", "--no-checkout", ws.upstream.as_uri(), str(blobless))
        git("checkout", "-q", "--detach", ws.pin, cwd=blobless)
        lazy = dev / "Harness" / "lazy"
        git("clone", "-q", "--no-checkout", str(blobless), str(lazy))
        git("checkout", "-q", "--detach", ws.pin, cwd=lazy)
        # The books live outside dev, as the PDFs and their text do on the packing machine.
        cls.books = ws.root / "books-source"
        git("clone", "-q", str(ws.upstream), str(cls.books / "pdfs"))
        git("checkout", "-q", ws.pin, cwd=cls.books / "pdfs")
        cls.personal = ws.root / "packer-config" / "personal-repos.txt"
        write(cls.personal, "%s\t%s\t%s\n" % (BOOKS, URL, ws.pin))
        text = cls.books / "text"
        write(text / "INDEX.md", "# The book library\n")
        write(text / "c" / "book.md", "=====PAGE 1=====\n")
        write(text / ".books.json", "{}\n")
        write(text / "c" / "half.md.partial", "torn\n")
        write(text / ".books.lock", "123\n")
        cls.dest = ws.root / "packed"
        cls.packed = cls.pack(cls.dest)

    @classmethod
    def pack(cls, dest, *args, src=None, reverse=None):
        books = ("--books-text", cls.books / "text", "--personal-from", cls.books,
                 "--personal-repos", cls.personal)
        return subprocess.run([BASH, str(PACK), str(src or cls.ws.dev), str(dest), *map(str, books),
                               "--reverse-from", str(reverse or cls.downloads), *map(str, args)],
                              env=cls.ws.env(), capture_output=True, encoding="utf-8", errors="replace",
                              timeout=300)

    def verify(self, dest):
        return subprocess.run([BASH, str(PACK), "verify", str(dest)], capture_output=True, encoding="utf-8",
                              errors="replace", timeout=120)

    def files(self, dest):
        return sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())

    def test_pack_writes_every_part_and_hashes_it(self):
        self.assertEqual(self.packed.returncode, 0, self.packed.stdout + self.packed.stderr)
        self.assertEqual(self.files(self.dest), [
            "README.txt", "SHA256SUMS", "books/Books-text.tar", "books/Library__pdfs.bundle",
            "clones/Library__lazy.git.tar", "clones/Library__thin.git.tar", "clones/Library__tool.bundle",
            "dev.bundle", "install.sh", "personal-repos.txt", "reverse/apktool.jar", "reverse/jdk-21.zip"])
        listed = sorted(line.split(" ", 1)[1].lstrip("*").replace("./", "", 1)
                        for line in (self.dest / "SHA256SUMS").read_text(encoding="utf-8").splitlines())
        self.assertEqual(listed, [f for f in self.files(self.dest) if f != "SHA256SUMS"])
        self.assertEqual(self.verify(self.dest).returncode, 0)

    def test_a_reverse_archive_that_differs_from_its_manifest_stops_the_pack(self):
        tampered = self.ws.root / "downloads-tampered"
        shutil.copytree(str(self.downloads), str(tampered))
        (tampered / "jdk" / "jdk-21.zip").write_bytes(b"not the jdk\n")
        dest = self.ws.root / "tampered-out"
        result = self.pack(dest, reverse=tampered)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("differs from Harness/setup/reverse-downloads.json", result.stdout)
        self.assertFalse((dest / "SHA256SUMS").exists())

    def test_a_shallow_clone_travels_without_its_credentials(self):
        with tarfile.open(str(self.dest / "clones" / "Library__thin.git.tar")) as tar:
            names = tar.getnames()
            config = tar.extractfile(".git/config").read().decode("utf-8")
        self.assertIn(URL, config)
        self.assertNotIn(TOKEN, config)
        self.assertNotIn("extraheader", config)
        self.assertEqual(names.count(".git/config"), 1)
        self.assertFalse([n for n in names if n.startswith((".git/hooks", ".git/logs", ".git/index"))])
        self.assertIn(".git/shallow", names)

    def test_a_partial_copy_travels_as_a_tar_that_can_fetch_what_it_lacks(self):
        with tarfile.open(str(self.dest / "clones" / "Library__lazy.git.tar")) as tar:
            config = tar.extractfile(".git/config").read().decode("utf-8")
        self.assertIn("promisor = true", config)
        self.assertIn(URL, config)

    def test_books_text_leaves_its_partial_and_lock_files_behind(self):
        with tarfile.open(str(self.dest / "books" / "Books-text.tar")) as tar:
            names = {n[2:] if n.startswith("./") else n for n in tar.getnames()}
        self.assertTrue({"INDEX.md", "c/book.md", ".books.json"} <= names, names)
        self.assertFalse([n for n in names if n.endswith((".partial", ".lock"))])

    def test_verify_catches_a_changed_or_an_unlisted_file(self):
        copy = self.ws.root / "usb-copy"
        shutil.copytree(str(self.dest), str(copy))
        self.addCleanup(shutil.rmtree, str(copy), True)
        with (copy / "clones" / "Library__tool.bundle").open("ab") as handle:
            handle.write(b"x")
        self.assertNotEqual(self.verify(copy).returncode, 0)
        shutil.rmtree(str(copy))
        shutil.copytree(str(self.dest), str(copy))
        write(copy / "stray.txt", "not packed\n")
        result = self.verify(copy)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stray.txt", result.stderr)

    def test_pack_refuses_a_folder_that_is_not_empty(self):
        dest = self.ws.root / "full"
        write(dest / "something", "here\n")
        self.assertNotEqual(self.pack(dest).returncode, 0)
        self.assertEqual(self.files(dest), ["something"])

    def test_pack_refuses_a_shallow_dev(self):
        # A bundle of a shallow repository says "complete history" and then cannot be cloned.
        src = self.ws.root / "dev-shallow"
        git("clone", "-q", "--depth", "1", self.ws.dev.as_uri(), str(src))
        dest = self.ws.root / "shallow-out"
        result = self.pack(dest, src=src)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shallow", result.stderr)
        self.assertFalse((dest / "dev.bundle").exists())

    def test_no_books_clone_leaves_only_the_books_clone_out(self):
        dest = self.ws.root / "no-books"
        result = self.pack(dest, "--no-books-clone")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("books/Library__pdfs.bundle", self.files(dest))
        self.assertNotIn("personal-repos.txt", self.files(dest))
        self.assertIn("books/Books-text.tar", self.files(dest))

    def test_a_personal_list_saved_with_crlf_still_packs_its_clones(self):
        crlf = self.ws.root / "personal-crlf.txt"
        crlf.write_bytes(self.personal.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        dest = self.ws.root / "crlf-out"
        result = self.pack(dest, "--personal-repos", crlf)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("books/Library__pdfs.bundle", self.files(dest))

    def test_a_missing_part_stops_the_pack_unless_its_flag_leaves_it_out(self):
        nowhere = self.ws.root / "no-such-books-text"
        dest = self.ws.root / "missing-text"
        result = self.pack(dest, "--books-text", nowhere)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--no-books-text", result.stdout)
        self.assertFalse((dest / "SHA256SUMS").exists())
        bare = subprocess.run([BASH, str(PACK), str(self.ws.dev), str(self.ws.root / "missing-reverse"),
                               "--books-text", str(self.books / "text"), "--personal-from", str(self.books),
                               "--personal-repos", str(self.personal)],
                              env=self.ws.env(), capture_output=True, encoding="utf-8", errors="replace",
                              timeout=300)
        self.assertNotEqual(bare.returncode, 0)
        self.assertIn("--no-reverse", bare.stdout)
        dest = self.ws.root / "left-out"
        result = self.pack(dest, "--books-text", nowhere, "--no-books-text", "--no-reverse")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("books/Books-text.tar", self.files(dest))
        self.assertFalse((dest / "reverse").exists())
        self.assertIn("0 reverse archives, books text no, 1 personal clones", result.stdout)

    def test_pack_stops_on_a_credential_file_in_any_branch(self):
        src = self.ws.root / "dev-with-secret"
        git("clone", "-q", str(self.ws.dev), str(src))
        for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.invalid")):
            git("config", key, value, cwd=src)
        git("checkout", "-q", "-b", "side", cwd=src)
        write(src / "Harness" / "auth.json", "{}\n")
        git("add", "-A", cwd=src)
        git("commit", "-q", "-m", "oops", cwd=src)
        git("checkout", "-q", "-", cwd=src)
        for row in ("Harness/tool", "Harness/thin", "Harness/lazy"):
            shutil.copytree(str(self.ws.dev / row), str(src / row), symlinks=True)
        dest = self.ws.root / "secret"
        result = self.pack(dest, src=src)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Harness/auth.json", result.stdout)
        self.assertFalse((dest / "SHA256SUMS").exists())

    def dev_copy(self, name):
        src = self.ws.root / name
        git("clone", "-q", str(self.ws.dev), str(src))
        for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.invalid")):
            git("config", key, value, cwd=src)
        for row in ROWS:
            shutil.copytree(str(self.ws.dev / row), str(src / row), symlinks=True)
        return src

    def test_pack_stops_on_a_credential_file_in_a_stash(self):
        # The bundle carries every ref, refs/stash and its untracked-files commit too.
        src = self.dev_copy("dev-with-stash")
        write(src / ".env", "TOKEN=abc\n")
        git("stash", "-q", "-u", cwd=src)
        dest = self.ws.root / "stash-out"
        result = self.pack(dest, src=src)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".env", result.stdout)
        self.assertFalse((dest / "SHA256SUMS").exists())

    def test_pack_stops_on_a_credential_file_deleted_from_the_tip(self):
        # A past commit still carries it, and so does the bundle.
        src = self.dev_copy("dev-with-history")
        write(src / ".env", "TOKEN=abc\n")
        git("add", "-A", cwd=src)
        git("commit", "-q", "-m", "oops", cwd=src)
        git("rm", "-q", ".env", cwd=src)
        git("commit", "-q", "-m", "gone", cwd=src)
        dest = self.ws.root / "history-out"
        result = self.pack(dest, src=src)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".env", result.stdout)
        self.assertFalse((dest / "SHA256SUMS").exists())

    def test_book_text_from_an_older_workspace_keeps_its_progress(self):
        # The old workspace named the state file .<its name>-books.json; books reads .books.json.
        text = self.ws.root / "old-text"
        write(text / "c" / "book.md", "=====PAGE 1=====\n")
        write(text / ".old-books.json", '{"books": {}}\n')
        dest = self.ws.root / "old-text-out"
        result = self.pack(dest, "--books-text", text)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with tarfile.open(str(dest / "books" / "Books-text.tar")) as tar:
            names = {n[2:] if n.startswith("./") else n for n in tar.getnames()}
        self.assertIn(".books.json", names)
        self.assertNotIn(".old-books.json", names)

    @unittest.skipUnless(python3_is_312(), "install.sh requires python3 3.12")
    def test_install_puts_dev_and_every_clone_at_its_pin(self):
        target = self.ws.root / "installed" / "dev"
        home = self.ws.home
        before = {name: digest(home / name) for name in (".profile", ".bash_profile", ".gitconfig")}
        result, calls = self.ws.run(self.dest / "install.sh", target, "--no-system", timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(git("rev-parse", "HEAD", cwd=target), git("rev-parse", "HEAD", cwd=self.ws.dev))
        self.assertEqual(git("remote", cwd=target), "")
        for key, value in SETTINGS.items():
            self.assertEqual(git("config", "--get", key, cwd=target), value, key)
        self.assertEqual((home / ".config" / "devarness" / "personal-repos.txt").read_text(encoding="utf-8"),
                         self.personal.read_text(encoding="utf-8"))
        for row in ROWS + (BOOKS,):
            clone = target / row
            self.assertEqual(git("rev-parse", "HEAD", cwd=clone), self.ws.pin, row)
            self.assertEqual(git("status", "--porcelain", cwd=clone), "", row)
            self.assertEqual(git("remote", "get-url", "origin", cwd=clone), URL, row)
        self.assertTrue((target / "Books" / "text" / "c" / "book.md").is_file())
        self.assertFalse((target / "Books" / "text" / "c" / "half.md.partial").exists())
        self.assertTrue([c for c in calls if c.startswith("new-device check")], calls)
        reverse = [c for c in calls if c.startswith("setup-reverse.py --from")]
        self.assertEqual(len(reverse), 1, calls)
        self.assertEqual([c for c in calls if c.split()[0] in TRIPWIRES], [])
        self.assertEqual({name: digest(home / name) for name in before}, before)
        if self.ws.links:
            # git checked the skill link out before its clone existed; it works now, and git sees no change.
            self.assertTrue(is_dir_link(target / ".claude" / "skills" / "thing"))
            self.assertTrue((home / ".claude" / "skills" / "thing" / "SKILL.md").is_file())
            self.assertEqual(git("status", "--porcelain", "--untracked-files=no", cwd=target), "")
        # Run again: everything is present and left alone.
        again, _ = self.ws.run(self.dest / "install.sh", target, "--no-system", timeout=300)
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("left alone", again.stdout)

    def test_install_verify_checks_the_usb_and_installs_nothing(self):
        # The spec's last step; a bare word used to be taken as the folder to install into.
        result, calls = self.ws.run(self.dest / "install.sh", "verify", "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("every file matches", result.stdout)
        self.assertFalse([c for c in calls if c.startswith("bootstrap")], calls)
        self.assertFalse(Path("verify").exists())
        copy = self.ws.root / "usb-stray"
        shutil.copytree(str(self.dest), str(copy))
        self.addCleanup(shutil.rmtree, str(copy), True)
        write(copy / "stray.txt", "not packed\n")
        result, _ = self.ws.run(copy / "install.sh", "verify")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stray.txt", result.stdout)

    @unittest.skipUnless(python3_is_312(), "install.sh requires python3 3.12")
    def test_install_refuses_a_damaged_payload_before_writing(self):
        copy = self.ws.root / "usb-damaged"
        shutil.copytree(str(self.dest), str(copy))
        self.addCleanup(shutil.rmtree, str(copy), True)
        with (copy / "dev.bundle").open("ab") as handle:
            handle.write(b"x")
        target = self.ws.root / "never"
        result, _ = self.ws.run(copy / "install.sh", target, "--no-system")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA256SUMS", result.stdout)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
