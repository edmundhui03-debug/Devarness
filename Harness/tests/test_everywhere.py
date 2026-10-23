"""Every dev command works from any folder, reached through a link in another bin folder.

Run: python Harness/tests/test_everywhere.py

bootstrap links each Harness/bin command into ~/.local/bin, and the owner runs
them from wherever he is. Here a temporary bin folder holds a link to each
command, and Git Bash runs it by name from a folder outside dev, with a scratch
HOME. Every probe is read-only. A probe must behave as the same probe run from
the dev root, must not crash, and where it prints a path, the path is in this
checkout. claude-start and codex-start always run the start check and then the
client, so they are tried on a copy in a stand-in dev whose start check and
client are fakes; nothing real is pulled or started.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "Harness" / "bin"
BASH = shutil.which("bash")
LAUNCHERS = ("claude-start", "codex-start")
SAME, EXIT, SHOWS_ROOT, SHOWS_MAIN = "same output", "same exit", "shows the dev root", "shows the main checkout"
# The main checkout, which is ROOT unless this is a linked worktree.
MAIN_ROOT = Path(subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                capture_output=True, encoding="utf-8", check=True).stdout.strip()).resolve().parent
# command: (read-only probe, what proves it found dev). SAME compares the whole
# output with a run from the dev root; EXIT only the status, for output that
# names the folder it ran in or the time; SHOWS_ROOT also needs a path in dev;
# SHOWS_MAIN a path in the main checkout, for memory that every worktree shares.
PROBES = {
    "agent-memory": (["where"], SHOWS_MAIN),
    "archify": (["skill"], SHOWS_ROOT),
    "books": ([], SAME),
    # playwright-cli prints its skill path relative to the folder it runs in.
    "browser": (["--agent", "peter", "--help"], EXIT),
    "dev-check": (["--only", "md-format-selftest", "--json"], SHOWS_ROOT),
    "diagram": (["profile"], SHOWS_ROOT),
    "fds-setup": (["--help"], SAME),
    "i18n": (["selftest"], SAME),
    "laya-service": (["--help"], SAME),
    "learn-claude": (["--help"], SAME),
    "library": (["search", "pdf"], SAME),
    "md-format": (["status"], SAME),
    "md-pages": (["--help"], SAME),
    "new-device": (["check", "--json"], SHOWS_ROOT),
    "ngspice-setup": (["--check"], SHOWS_ROOT),
    "notify": (["check"], SAME),
    "ocr": (["--help"], SAME),
    "rea": (["--version"], SAME),
    "reverse": (["java", "-version"], SAME),
    "start-check": (["--check", "--text"], EXIT),
    "statusline": (["--preview"], EXIT),
    "task-recall": (["--list"], SAME),
    "tieitup": (["help"], SAME),
    "understand": (["root"], SHOWS_ROOT),
    "update-tools": (["status"], SAME),
    "video-study": (["check"], SAME),
}
FAKE_CLIENT = "#!/usr/bin/env python3\nimport os, sys\nprint('client in', os.getcwd(), sys.argv[1:])\n"
FAKE_GATE = "#!/usr/bin/env bash\necho 'START COMPLETE — READY'\n"


def can_symlink(folder):
    try:
        os.symlink(str(folder), str(folder / "probe-link"), target_is_directory=True)
        os.rmdir(str(folder / "probe-link")) if os.name == "nt" else os.remove(str(folder / "probe-link"))
        return True
    except OSError:
        return False


def link(target, folder):
    """A link named like the command, as bootstrap makes in ~/.local/bin."""
    folder.mkdir(parents=True, exist_ok=True)
    os.symlink(str(target), str(folder / target.name))


def shows(path, text):
    """True when text names path, in Windows or POSIX spelling, with JSON's doubled backslashes."""
    text = text.replace("\\\\", "\\")
    spellings = {str(path), path.as_posix(), str(path).replace("\\", "/")}
    if os.name == "nt":
        drive, rest = path.as_posix().split(":", 1)
        spellings.add("/" + drive.lower() + rest)
    return any(s.lower() in text.lower() for s in spellings)


@unittest.skipUnless(BASH, "bash is required")
class EverywhereTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="everywhere-")
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name).resolve()
        if not can_symlink(self.tmp):
            self.skipTest("this account cannot make symlinks")
        self.home = self.tmp / "home"
        self.elsewhere = self.tmp / "elsewhere"
        for folder in (self.home, self.elsewhere):
            folder.mkdir()
        self.bin = self.tmp / "bin"

    def run_command(self, command, argv, cwd):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                   CODEX_HOME=str(self.home / ".codex"), PYTHONIOENCODING="utf-8",
                   PATH=os.pathsep.join([str(self.bin), os.environ.get("PATH", "")]))
        env.pop("DEVARNESS_HOME", None)
        done = subprocess.run([BASH, "-c", 'exec "$0" "$@"', command, *argv], cwd=str(cwd), env=env,
                              capture_output=True, encoding="utf-8", errors="replace", timeout=300,
                              stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout + done.stderr

    def test_every_command_has_a_probe(self):
        self.assertEqual(sorted([*PROBES, *LAUNCHERS]),
                         sorted(p.name for p in BIN.iterdir() if p.is_file()))

    def test_every_command_works_from_outside_dev_through_a_link(self):
        for name in PROBES:
            link(BIN / name, self.bin)
        for name, (argv, proof) in sorted(PROBES.items()):
            with self.subTest(command=name):
                code, out = self.run_command(name, argv, self.elsewhere)
                home_code, home_out = self.run_command((BIN / name).as_posix(), argv, ROOT)
                self.assertNotIn("Traceback (most recent call last)", out, out[-2000:])
                self.assertEqual(code, home_code, "outside dev:\n%s\ninside dev:\n%s" % (out[-1500:], home_out[-1500:]))
                if proof == SAME:
                    self.assertEqual(out, home_out)
                if proof in (SHOWS_ROOT, SHOWS_MAIN):
                    root = MAIN_ROOT if proof == SHOWS_MAIN else ROOT
                    self.assertTrue(shows(root, out) or re.sub(r"[^A-Za-z0-9]", "-", str(root)) in out, out[-1500:])

    def test_the_two_house_gates_check_the_folder_they_run_in(self):
        for name in ("i18n", "md-format"):
            link(BIN / name, self.bin)
        code, out = self.run_command("i18n", ["check"], self.elsewhere)
        if "needs markitdown's python" in out:
            self.skipTest(out.strip())
        self.assertNotIn("Traceback (most recent call last)", out, out[-2000:])
        self.assertIn("not in a git repository", out)
        self.assertNotEqual(code, 0)
        # In another repository md-format checks that one's Markdown, as i18n does.
        subprocess.run(["git", "init", "-q", str(self.elsewhere)], check=True, capture_output=True)
        (self.elsewhere / "note.md").write_text("no title and no header block\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.elsewhere), "add", "note.md"], check=True, capture_output=True)
        code, out = self.run_command("md-format", ["check"], self.elsewhere)
        self.assertEqual(code, 1, out)
        self.assertIn("note.md", out)
        self.assertIn("1 files", out)

    def test_the_agent_launchers_start_the_client_in_their_own_dev(self):
        dev = self.tmp / "dev"
        gate = dev / ".claude" / "hooks" / "session-start.sh"
        gate.parent.mkdir(parents=True)
        gate.write_text(FAKE_GATE, encoding="utf-8", newline="\n")
        for name in LAUNCHERS:
            copy = dev / "Harness" / "bin" / name
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(BIN / name), str(copy))
            link(copy, self.bin)
        for client in ("claude", "codex"):
            (self.bin / client).write_text(FAKE_CLIENT, encoding="utf-8", newline="\n")
        for name in LAUNCHERS:
            with self.subTest(command=name):
                code, out = self.run_command(name, ["--version"], self.elsewhere)
                self.assertEqual(code, 0, out)
                self.assertIn("START COMPLETE", out)
                self.assertIn("client in %s ['--version']" % dev, out)


if __name__ == "__main__":
    unittest.main()
