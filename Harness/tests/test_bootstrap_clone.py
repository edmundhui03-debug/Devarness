"""bootstrap.sh restores the pinned clones from the USB, links the skills for every folder,
registers the MCP servers for the user, and --no-system stays out of the system.

Run: python3 Harness/tests/test_bootstrap_clone.py

Each test builds a throwaway workspace: a copy of bootstrap.sh, a repos.txt,
dev's skill folders (one skill of its own, links into a clone that does not
exist yet), and a stand-in for every script bootstrap calls, each of which
only logs its arguments. Stand-ins for schtasks, ssh-keygen, ssh-keyscan,
powershell and the agent clients sit first on PATH as tripwires. The fixture
upstream is a local repository whose pin is not its tip and which holds a
symlink, a skill, REA's and reverse-skill's skill folders and reverse-skill's
payload folder, so a restore must land on the pin with real links. No
network, key, scheduled task or real home is touched. test_usb.py reuses the
Workspace.
"""

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2]
BOOTSTRAP = SOURCE / "Harness" / "bootstrap.sh"
BASH = shutil.which("bash")
URL = "https://example.invalid/tool.git"
SETTINGS = {"core.autocrlf": "false", "core.eol": "lf", "core.symlinks": "true", "core.longpaths": "true"}
PAYLOAD = "skills/pentest-tools/src-hunter/references/payloader"
REA_SKILL = "skills/reverse-engineer-anything"
ROUTER_SKILL = "plugins/reverse-skill/skills/reverse-skill-router"

# Everything bootstrap runs from the workspace; each stand-in logs and succeeds.
SCRIPTS = ("Harness/setup-library.py", "Harness/setup-task-support.py", "Harness/setup-learn-claude.py",
           "Harness/setup-browser-docs.py", "Harness/knowledge-tools-sync.py", "Harness/setup-laya.py",
           "Harness/setup-reverse.py", "Harness/setup-vercel-skills.py", "Harness/bin/update-tools", "Harness/bin/dev-check",
           "Harness/bin/start-check", "Harness/bin/new-device", "Harness/bin/library",
           "Harness/codex-setup.py")
TRIPWIRES = ("schtasks", "ssh-keygen", "ssh-keyscan", "ssh", "powershell", "claude", "codex", "pi")
SYSTEM_STEPS = ("update-tools install-daily", "dev-check --install-daily", "setup-laya.py --install",
                "knowledge-tools-sync.py --install")
FAKE_PY = """#!/usr/bin/env python3
import os, sys
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
    log.write(" ".join([os.path.basename(sys.argv[0])] + sys.argv[1:])
              + " | uv_cache=" + os.environ.get("UV_CACHE_DIR", "") + "\\n")
"""
FAKE_SH = """#!/bin/sh
printf '%s %s\\n' "$(basename "$0")" "$*" >> "$FAKE_LOG"
"""
# Git Bash puts its own folders first while it starts, so the stand-ins go first again here.
HARNESS = """fake="$FAKE_BIN"
command -v cygpath >/dev/null 2>&1 && fake="$(cygpath -u "$FAKE_BIN")"
export PATH="$fake:$PATH"
exec bash "$@"
"""


def write(path, text, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Path.open, not write_text: write_text took newline= only from Python 3.10.
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          encoding="utf-8").stdout.strip()


def can_symlink(folder):
    try:
        os.symlink("target", str(folder / "probe-link"))
        os.remove(str(folder / "probe-link"))
        return True
    except OSError:
        return False


def file_link(target, at):
    """A link as git makes one before its target exists: on Windows, a file link nothing can enter."""
    at.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target.replace("/", "\\") if os.name == "nt" else target, str(at))


def is_dir_link(path):
    """A link stat can follow into a folder; on Windows it carries the directory attribute."""
    if not os.path.islink(str(path)) or not os.path.isdir(str(path)):
        return False
    return os.name != "nt" or bool(os.lstat(str(path)).st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY)


def make_upstream(folder):
    """A repository whose first commit, the pin, holds a.txt, a symlink to it, skills and a payload; its tip moves on."""
    git("init", "-q", str(folder))
    for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.invalid"),
                       ("core.autocrlf", "false")):
        git("config", key, value, cwd=folder)
    write(folder / "a.txt", "one\n")
    for skill in ("skills/thing", REA_SKILL, ROUTER_SKILL):
        write(folder / skill / "SKILL.md", "---\nname: %s\n---\n" % skill.rsplit("/", 1)[1])
    write(folder / PAYLOAD / "flagged.txt", "antivirus bait\n")
    link = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=folder, input="a.txt",
                          capture_output=True, text=True, check=True).stdout.strip()
    git("update-index", "--add", "--cacheinfo", "120000," + link + ",link", cwd=folder)
    # An executable, so a restore that leaves core.filemode unset on Windows shows it as changed.
    run = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=folder, input="#!/bin/sh\n",
                         capture_output=True, text=True, check=True).stdout.strip()
    git("update-index", "--add", "--cacheinfo", "100755," + run + ",run.sh", cwd=folder)
    git("add", "a.txt", "skills", "plugins", cwd=folder)
    git("commit", "-q", "-m", "pin", cwd=folder)
    pin = git("rev-parse", "HEAD", cwd=folder)
    git("tag", "pin", cwd=folder)
    write(folder / "a.txt", "two\n")
    git("commit", "-q", "-am", "tip", cwd=folder)
    return pin


def tar_git(clone, archive):
    with tarfile.open(str(archive), "w") as tar:
        tar.add(str(clone / ".git"), arcname=".git")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class Workspace:
    """A temporary root with an upstream, a USB payload folder, a home and a dev workspace."""

    def __init__(self, cleanup, rows=("Harness/tool",)):
        temp = tempfile.TemporaryDirectory()
        cleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.upstream = self.root / "upstream"
        self.pin = make_upstream(self.upstream)
        self.payload = self.root / "usb"
        (self.payload / "clones").mkdir(parents=True)
        self.home = self.root / "home"
        write(self.home / ".profile", "# the owner's profile\n")
        write(self.home / ".bash_profile", "# the owner's bash profile\n")
        write(self.home / ".gitconfig", "[user]\n\tname = Owner\n\temail = owner@example.invalid\n")
        self.dev = self.root / "dev"
        self.log = self.root / "fake.log"
        self.bin = self.root / "fake-bin"
        # uv too: install.sh may ask its version, never install a tool under --no-system.
        for name in TRIPWIRES + ("uv",):
            write(self.bin / name, FAKE_SH, executable=True)
        write(self.root / "harness.sh", HARNESS)
        self.links = can_symlink(self.root)
        self.make_dev(self.dev, rows)

    def make_dev(self, dev, rows):
        write(dev / "Harness" / "bootstrap.sh", BOOTSTRAP.read_text(encoding="utf-8"), executable=True)
        write(dev / "Harness" / "repos.txt", "# fixture\n" + "".join(
            "%s\t%s\t%s\n" % (row, URL, self.pin) for row in rows))
        for script in SCRIPTS:
            write(dev / script, FAKE_PY, executable=True)
        # dev's own skill, and links into the first clone, made before the clone exists.
        write(dev / ".claude" / "skills" / "own" / "SKILL.md", "---\nname: own\n---\n")
        if self.links:
            file_link("../../%s/skills/thing" % rows[0], dev / ".claude" / "skills" / "thing")
            file_link("../../.claude/skills/own", dev / ".agents" / "skills" / "own")
            file_link("../../%s/skills/thing" % rows[0], dev / ".agents" / "skills" / "thing")

    def bundle(self, name="Library__tool"):
        git("bundle", "create", "-q", str(self.payload / "clones" / (name + ".bundle")), "--all",
            cwd=self.upstream)

    def shallow_tar(self, name="Library__tool"):
        shallow = self.root / "shallow"
        git("clone", "-q", "--depth", "1", "--branch", "pin", self.upstream.as_uri(), str(shallow))
        # pack.sh rebuilds the config with the remote alone, made on another machine.
        for key in ("core.filemode", "core.symlinks", "core.ignorecase", "core.bare"):
            subprocess.run(["git", "config", "--unset", key], cwd=shallow)
        tar_git(shallow, self.payload / "clones" / (name + ".git.tar"))

    def env(self):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), FAKE_LOG=self.log.as_posix(),
                   FAKE_BIN=str(self.bin), PATH=os.pathsep.join([str(self.bin), os.environ.get("PATH", "")]))
        for key in ("UV_CACHE_DIR", "npm_config_cache", "MSYS", "CODEX_HOME"):
            env.pop(key, None)
        return env

    def run(self, script, *args, timeout=180):
        result = subprocess.run([BASH, str(self.root / "harness.sh"), str(script), *map(str, args)],
                                env=self.env(), capture_output=True, encoding="utf-8", errors="replace",
                                timeout=timeout)
        calls = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        return result, calls

    def bootstrap(self, *args):
        return self.run(self.dev / "Harness" / "bootstrap.sh", *args)


@unittest.skipUnless(BASH, "bash is required")
class OfflineRestoreTests(unittest.TestCase):
    def assert_at_pin(self, ws, clone):
        self.assertEqual(git("rev-parse", "HEAD", cwd=clone), ws.pin)
        self.assertEqual(git("status", "--porcelain", cwd=clone), "")
        self.assertEqual(git("remote", "get-url", "origin", cwd=clone), URL)
        for key, value in SETTINGS.items():
            self.assertEqual(git("config", "--get", key, cwd=clone), value, key)
        self.assertEqual((clone / "a.txt").read_bytes(), b"one\n")
        if ws.links:
            self.assertTrue(os.path.islink(str(clone / "link")), "the tracked symlink is not a link")
        self.assertFalse((clone.parent / (clone.name + ".partial")).exists())

    def test_a_bundled_clone_is_restored_at_its_pin(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_at_pin(ws, ws.dev / "Harness" / "tool")

    def test_a_shallow_clone_is_restored_from_a_tar_of_its_git(self):
        ws = Workspace(self.addCleanup)
        ws.shallow_tar()
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_at_pin(ws, ws.dev / "Harness" / "tool")

    def test_a_clone_in_a_subfolder_is_found_by_its_flattened_name(self):
        ws = Workspace(self.addCleanup, rows=("Harness/pcb/tool",))
        ws.bundle("Library__pcb__tool")
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_at_pin(ws, ws.dev / "Harness" / "pcb" / "tool")

    def test_the_books_folder_of_the_payload_is_searched_too(self):
        ws = Workspace(self.addCleanup, rows=("Harness/pdfs",))
        (ws.payload / "books").mkdir()
        git("bundle", "create", "-q", str(ws.payload / "books" / "Library__pdfs.bundle"), "--all",
            cwd=ws.upstream)
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_at_pin(ws, ws.dev / "Harness" / "pdfs")

    def test_a_personal_clone_from_the_owners_config_is_restored_too(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        (ws.payload / "books").mkdir()
        git("bundle", "create", "-q", str(ws.payload / "books" / "Library__pdfs.bundle"), "--all",
            cwd=ws.upstream)
        # No newline at the end: the last row still counts.
        write(ws.home / ".config" / "devarness" / "personal-repos.txt",
              "# the owner's own\nHarness/pdfs\t%s\t%s" % (URL, ws.pin))
        git("init", "-q", str(ws.dev))
        for attempt in (1, 2):          # the exclude line is written once
            result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_at_pin(ws, ws.dev / "Harness" / "tool")
        self.assert_at_pin(ws, ws.dev / "Harness" / "pdfs")
        # Kept out of git on this device only: its name never goes into a tracked file.
        exclude = (ws.dev / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(exclude.splitlines().count("/Harness/pdfs"), 1, exclude)
        self.assertEqual(git("status", "--porcelain", "--", "Harness/pdfs", cwd=ws.dev), "")

    def test_a_clone_already_at_its_pin_is_left_alone(self):
        ws = Workspace(self.addCleanup)
        clone = ws.dev / "Harness" / "tool"
        git("clone", "-q", str(ws.upstream), str(clone))
        git("checkout", "-q", ws.pin, cwd=clone)
        write(clone / "mine.txt", "untracked work\n")
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")       # the payload is empty
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("present at its pin: Harness/tool", result.stdout)
        self.assertTrue((clone / "mine.txt").is_file())

    def test_a_clone_missing_from_the_payload_is_a_problem(self):
        ws = Workspace(self.addCleanup)
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not on the USB", result.stdout)
        self.assertFalse((ws.dev / "Harness" / "tool").exists())
        self.assertFalse((ws.dev / "Harness" / "tool.partial").exists())

    def test_offline_needs_a_folder(self):
        ws = Workspace(self.addCleanup)
        result, calls = ws.bootstrap("--offline")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(calls, [])


@unittest.skipUnless(BASH, "bash is required")
class ReverseToolTests(unittest.TestCase):
    ROWS = ("Harness/rea", "Harness/reverse-skill")

    def restored(self):
        ws = Workspace(self.addCleanup, rows=self.ROWS)
        for row in self.ROWS:
            ws.bundle(row.replace("/", "__"))
        return ws

    def test_reverse_skill_is_restored_without_its_payload_and_still_at_its_pin(self):
        ws = self.restored()
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        clone = ws.dev / "Harness" / "reverse-skill"
        self.assertFalse((clone / PAYLOAD).exists())
        self.assertTrue((clone / ROUTER_SKILL / "SKILL.md").is_file())
        self.assertEqual(git("rev-parse", "HEAD", cwd=clone), ws.pin)
        self.assertEqual(git("status", "--porcelain", cwd=clone), "")
        self.assertTrue((ws.dev / "Harness" / "rea" / PAYLOAD / "flagged.txt").is_file())   # only reverse-skill's

    def test_a_reverse_skill_clone_already_present_loses_its_payload_too(self):
        ws = Workspace(self.addCleanup, rows=("Harness/reverse-skill",))
        clone = ws.dev / "Harness" / "reverse-skill"
        git("clone", "-q", str(ws.upstream), str(clone))
        git("checkout", "-q", ws.pin, cwd=clone)
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((clone / PAYLOAD).exists())
        self.assertEqual(git("rev-parse", "HEAD", cwd=clone), ws.pin)

    def test_the_reverse_runtime_installs_from_the_usb_when_it_is_there(self):
        ws = self.restored()
        write(ws.payload / "reverse" / "apktool_3.0.2.jar", "jar\n")
        result, calls = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        runs = [c for c in calls if c.startswith("setup-reverse.py --from")]
        self.assertEqual(len(runs), 1, calls)
        self.assertIn("usb/reverse", runs[0].split(" | ")[0].replace("\\", "/"))

    def test_without_the_archives_the_reverse_runtime_is_a_note(self):
        ws = self.restored()
        result, calls = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse([c for c in calls if c.startswith("setup-reverse.py")], calls)
        self.assertIn("setup-reverse.py --from", result.stdout)


@unittest.skipUnless(BASH, "bash is required")
class SkillTests(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace(self.addCleanup, rows=("Harness/tool", "Harness/rea", "Harness/reverse-skill"))
        if not self.ws.links:
            self.skipTest("this account cannot make symlinks")
        for row in ("Harness/tool", "Harness/rea", "Harness/reverse-skill"):
            self.ws.bundle(row.replace("/", "__"))

    def test_skill_links_made_before_their_clone_work_after_the_restore(self):
        result, _ = self.ws.bootstrap("--offline", self.ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for link in (".claude/skills/thing", ".agents/skills/thing", ".agents/skills/own"):
            self.assertTrue(is_dir_link(self.ws.dev / link), link)
            self.assertTrue((self.ws.dev / link / "SKILL.md").is_file(), link)

    def test_every_skill_with_reas_and_the_router_is_linked_for_every_folder(self):
        mine = self.ws.home / ".claude" / "skills" / "own"
        write(mine / "SKILL.md", "the owner's own skill\n")
        for attempt in (1, 2):          # a second run changes nothing
            result, _ = self.ws.bootstrap("--offline", self.ws.payload, "--no-system")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for folder in (".claude/skills", ".agents/skills"):
            for name in ("thing", "reverse-engineer-anything", "reverse-skill-router"):
                self.assertTrue(is_dir_link(self.ws.home / folder / name), folder + "/" + name)
                self.assertTrue((self.ws.home / folder / name / "SKILL.md").is_file(), folder + "/" + name)
        self.assertTrue(is_dir_link(self.ws.home / ".agents" / "skills" / "own"))
        self.assertFalse(os.path.islink(str(mine)))
        self.assertEqual((mine / "SKILL.md").read_text(encoding="utf-8"), "the owner's own skill\n")
        self.assertIn("kept", result.stdout)


@unittest.skipUnless(BASH, "bash is required")
class SystemTests(unittest.TestCase):
    PROFILES = (".profile", ".bash_profile", ".gitconfig")

    def test_no_system_leaves_the_home_and_the_scheduler_alone(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        before = {name: digest(ws.home / name) for name in self.PROFILES}
        result, calls = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({name: digest(ws.home / name) for name in self.PROFILES}, before)
        self.assertFalse((ws.home / ".ssh").exists())
        self.assertFalse((ws.home / ".codex").exists())
        self.assertEqual([c for c in calls if c.split()[0] in TRIPWIRES], [])
        self.assertFalse([c for c in calls if c.startswith("uv tool")], calls)
        for step in SYSTEM_STEPS:
            self.assertFalse([c for c in calls if c.startswith(step)], step + " ran under --no-system")
        self.assertIn("would register laya", result.stdout)
        self.assertIn("would register rea", result.stdout)
        # The runtimes still install, with their package caches inside the checkout.
        library = [c for c in calls if c.startswith("setup-library.py --install")]
        self.assertEqual(len(library), 1, calls)
        cache = os.path.normcase(str(Path(library[0].split("uv_cache=", 1)[1]).resolve()))
        self.assertTrue(cache.startswith(os.path.normcase(str(ws.dev.resolve()))), cache)
        self.assertTrue([c for c in calls if c.startswith("start-check --check --text")], calls)
        if ws.links:
            self.assertTrue(os.path.islink(str(ws.home / ".local" / "bin" / "start-check")))

    def test_without_no_system_the_daily_runs_and_laya_are_registered(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        result, calls = ws.bootstrap("--offline", ws.payload)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for step in SYSTEM_STEPS:
            self.assertTrue([c for c in calls if c.startswith(step)], step + " did not run")
        self.assertTrue([c for c in calls if c.startswith("ssh-keygen")], calls)
        self.assertIn(".local/bin", (ws.home / ".bash_profile").read_text(encoding="utf-8"))
        self.assertEqual((ws.home / ".profile").read_text(encoding="utf-8"), "# the owner's profile\n")
        if os.name == "nt":
            self.assertTrue([c for c in calls if c.startswith("powershell")], calls)
        # No GitHub remote is needed: an unauthorised key never stops the run.
        self.assertTrue([c for c in calls if c.startswith("start-check --check --text")], calls)

    def test_without_no_system_laya_and_rea_are_mcp_servers_for_the_user(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        codex_config = ws.home / ".codex" / "config.toml"
        for attempt in (1, 2):          # a second run adds nothing twice, and refreshes a stale entry
            result, calls = ws.bootstrap("--offline", ws.payload)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            stale = codex_config.read_text(encoding="utf-8").replace("tool_timeout_sec = 400", "tool_timeout_sec = 1")
            if attempt == 1:
                codex_config.write_text(stale, encoding="utf-8", newline="\n")
        added = [c for c in calls if c.startswith("claude mcp add-json --scope user")]
        self.assertEqual(len(added), 4, calls)      # laya and rea, each run
        laya = [c for c in added if c.split()[5] == "laya"][0]
        rea = [c for c in added if c.split()[5] == "rea"][0]
        self.assertIn("'.local/bin/laya-service'", laya)
        self.assertTrue(rea.endswith('"mcp"]}'), rea)
        config = (ws.home / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertEqual(config.count("[mcp_servers.laya]"), 1, config)
        self.assertEqual(config.count("[mcp_servers.rea]"), 1, config)
        self.assertIn("'.local/bin/rea'), run_name='__main__')\", \"mcp\"]\nstartup_timeout_sec = 60\n"
                      "tool_timeout_sec = 400", config)

    def test_the_library_index_is_built_after_every_install_and_before_the_check(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        result, calls = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        names = [c.split(" |")[0] for c in calls]
        self.assertIn("library refresh", names, calls)
        refresh = names.index("library refresh")
        self.assertLess(names.index("setup-library.py --install"), refresh)
        self.assertLess(max(i for i, c in enumerate(names) if c.startswith("setup-browser-docs.py")), refresh)
        self.assertLess(refresh, names.index("start-check --check --text"))

    def test_a_launcher_that_cannot_be_linked_is_a_problem(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        write(ws.home / ".local","a file where the folder should be\n")
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("FAILED", result.stdout)
        self.assertNotIn("bootstrap complete", result.stdout)

    def test_a_dangling_launcher_dev_no_longer_has_is_removed(self):
        ws = Workspace(self.addCleanup)
        if not ws.links:
            self.skipTest("this account cannot make symlinks")
        ws.bundle()
        folder = ws.home / ".local" / "bin"
        folder.mkdir(parents=True)
        os.symlink(str(ws.dev / "Harness" / "bin" / "gone"), str(folder / "gone"))
        os.symlink(str(ws.root / "elsewhere" / "theirs"), str(folder / "theirs"))
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(os.path.lexists(str(folder / "gone")))
        self.assertTrue(os.path.islink(str(folder / "theirs")), "a link that is not dev's was removed")

    def test_a_command_of_the_same_name_that_is_not_devs_is_kept_and_named(self):
        ws = Workspace(self.addCleanup)
        if not ws.links:
            self.skipTest("this account cannot make symlinks")
        ws.bundle()
        theirs = ws.home / ".local" / "bin" / "library"
        write(theirs, "another tool's launcher\n")
        result, _ = ws.bootstrap("--offline", ws.payload, "--no-system")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(theirs.read_text(encoding="utf-8"), "another tool's launcher\n")
        self.assertIn("~/.local/bin/library is not dev's", result.stdout)

    def test_without_no_system_superpowers_goes_to_claude_then_codex(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        result, calls = ws.bootstrap("--offline", ws.payload)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        names = [c.split(" |")[0] for c in calls]
        self.assertIn("claude plugin install superpowers@claude-plugins-official", names, calls)
        self.assertIn("codex-setup.py", names, calls)
        self.assertLess(names.index("claude plugin install superpowers@claude-plugins-official"),
                        names.index("codex-setup.py"))
        self.assertIn("uv tool install markitdown[all]==0.1.8", names, calls)

    def test_superpowers_already_installed_is_not_installed_again(self):
        ws = Workspace(self.addCleanup)
        ws.bundle()
        write(ws.home / ".claude" / "plugins" / "installed_plugins.json",
              '{"plugins": {"superpowers@claude-plugins-official": [{"scope": "user"}]}}\n')
        result, calls = ws.bootstrap("--offline", ws.payload)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse([c for c in calls if c.startswith("claude plugin install")], calls)
        self.assertTrue([c for c in calls if c.startswith("codex-setup.py")], calls)

    def test_a_network_clone_finishes_at_its_pin_and_reverse_skill_without_its_payload(self):
        rows = ("Harness/tool", "Harness/reverse-skill")
        ws = Workspace(self.addCleanup, rows=rows)
        write(ws.dev / "Harness" / "repos.txt", "".join(
            "%s\t%s\t%s\n" % (row, ws.upstream.as_uri(), ws.pin) for row in rows))
        result, _ = ws.bootstrap("--no-system")
        out = result.stdout + result.stderr
        self.assertNotIn("unbound variable", out)
        self.assertEqual(result.returncode, 0, out)
        for row in rows:
            clone = ws.dev / row
            self.assertEqual(git("rev-parse", "HEAD", cwd=clone), ws.pin)
            self.assertEqual((clone / "a.txt").read_bytes(), b"one\n")
            self.assertTrue((clone / ROUTER_SKILL / "SKILL.md").is_file())
        self.assertTrue((ws.dev / rows[0] / PAYLOAD / "flagged.txt").is_file())
        self.assertFalse((ws.dev / rows[1] / PAYLOAD).exists())

    def test_the_launcher_loop_is_devs_command_list_in_order(self):
        names = ("start-check library claude-start codex-start statusline dev-check update-tools new-device "
                 "task-recall tieitup md-format i18n agent-memory notify laya-service books video-study ocr browser "
                 "md-pages understand diagram archify learn-claude ngspice-setup fds-setup rea reverse")
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("for b in %s; do" % names, text)
        for gone in ("hindsight", "Hindsight", "mirror", "Demo Widget", "Demo_Widget"):
            self.assertNotIn(gone, text)


if __name__ == "__main__":
    unittest.main()
