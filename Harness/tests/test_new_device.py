#!/usr/bin/env python3
"""new-device regressions on disposable dev clones and homes.

Run: python3 Harness/tests/test_new_device.py
     python3 -m unittest discover -s Harness/tests -p 'test_new_device.py' -v

Each test builds a stand-in dev repository, clones it the way a new device
does, and rebuilds only the layers the test needs: one pinned vendored clone,
the local settings and the launcher links in a fake home. Git runs with no
system or global configuration, so this machine's settings cannot leak into a
result, and the tool runs as a subprocess, the way a new device runs it.
DEVARNESS_NEWDEVICE_TOOL points the suite at a mutated copy of the tool, which is how
each test was shown to fail without the behaviour it guards.

The portable bootstrap excludes unrelated project integrations and device
registration state. These disposable fixtures exercise the supported layers.
dev may have no remote: an absent origin is a note. Every pinned clone counts,
the tracked ones and the owner's personal-repos.txt in the given home.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[2]
TOOL = Path(os.environ.get("DEVARNESS_NEWDEVICE_TOOL") or SOURCE / "Harness" / "bin" / "new-device")
DEVARNESS_REMOTE = "git@github.com:owner/dev.git"      # a stand-in: the owner has not made it yet
LAYERS = ["checkout", "git-settings", "vendored-clones", "local-settings", "launchers",
          "skill-links", "mcp-servers", "superpowers", "markitdown", "knowledge-tools", "library-index",
          "separate-projects", "labs", "reverse-tools", "daily-run", "memory", "notify",
          "laya", "statusline-tools", "pi"]
REQUIRED = ["checkout", "vendored-clones", "local-settings", "launchers", "skill-links", "mcp-servers",
            "superpowers", "markitdown", "knowledge-tools", "library-index"]
# What bootstrap's system steps install, missing on a clone where nothing was rebuilt.
SYSTEM_LAYERS = ["skill-links", "mcp-servers", "superpowers", "markitdown", "knowledge-tools", "library-index"]
# Stands in for Harness/knowledge-tools-sync.py: prepared once Harness/.runtime/knowledge-ready exists.
KNOWLEDGE = '''import sys
from pathlib import Path
if sys.argv[1:] != ["--check"]:
    sys.exit(2)
sys.exit(0 if (Path(__file__).parent / ".runtime" / "knowledge-ready").is_file() else 1)
'''
HEALTHY_INDEX = json.dumps({"schema": 2, "fingerprints": {}, "entries": [], "diagnostics": [], "router": []})
BOOTSTRAP = "Harness/bootstrap.sh"
WINDOWS_BOOTSTRAP = "export MSYS=winsymlinks:nativestrict; Harness/bootstrap.sh"
WINDOWS_CLONE = ("git clone -c core.autocrlf=false -c core.eol=lf -c core.symlinks=true -c core.longpaths=true "
                 "<dev's remote, or the USB's dev bundle> ~/dev")
CLONE = WINDOWS_CLONE          # every device clones with the four settings (Setup/NEW_DEVICE.md)
DASH = "—"
# What would let this machine's identity, git location, memory settings or an
# earlier override reach a result.
LEAKS = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_DIR",
         "GIT_WORK_TREE", "GIT_SSH_COMMAND", "DEVARNESS_MEMORY_DIR", "CLAUDE_CONFIG_DIR", "DEVARNESS_NEWDEVICE_PLATFORM",
         "DEVARNESS_NEWDEVICE_TIMEOUT", "DEVARNESS_NO_SYSTEM")
ENV = dict({key: value for key, value in os.environ.items() if key not in LEAKS},
           GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, PYTHONIOENCODING="utf-8")
# Stand-ins for agent-memory, which is built separately: one that answers the way
# its interface says, one that fails, and one that never answers.
WHERE = '''import sys
from pathlib import Path
if sys.argv[1:] != ["where"]:
    sys.exit(2)
print(Path.home() / ".claude" / "projects" / "-device-dev" / "memory")
'''
# Prints a folder that exists, then fails: a failed answer must not be trusted.
BROKEN_WHERE = "import sys\nfrom pathlib import Path\nprint(Path.home())\nsys.exit(1)\n"
SILENT_WHERE = "import time\ntime.sleep(60)\n"
# Stands in for Harness/setup-reverse.py: ready once Harness/.runtime/reverse-ready
# exists; it refuses anything but the fast --check, so new-device never runs the doctor.
REVERSE = '''import sys
from pathlib import Path
if sys.argv[1:] != ["--check"]:
    sys.exit(2)
if (Path(__file__).parent / ".runtime" / "reverse-ready").is_file():
    sys.exit(0)
print("reverse runtime:")
print("  jdk      MISSING")
print("  rea      MISSING")
sys.exit(1)
'''
# Loaded into the tool's interpreter by the network test: any socket use leaves a mark.
GUARD = '''import pathlib, sys
def _refuse(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto"):
        pathlib.Path({marker!r}).write_text(event)
        raise RuntimeError("new-device opened a socket")
sys.addaudithook(_refuse)
'''


def git(repo, *args, env=None):
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          env=env or ENV, timeout=60)
    if done.returncode:
        raise AssertionError("git {} failed: {}".format(" ".join(args), done.stderr))
    return done.stdout.strip()


def commit_all(repo, message):
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=Owner", "-c", "user.email=owner@example.com", "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def symlink(target, link):
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError) as error:
        raise unittest.SkipTest("this system cannot make symlinks: {}".format(error))


def remove_tree(path):
    def writable(function, target, _):
        os.chmod(target, 0o700)
        function(target)
    shutil.rmtree(str(path), onerror=writable)


def snapshot(root):
    """Every entry under root: link targets, folder times, file bytes and times."""
    state = {}
    for folder, folders, files in os.walk(str(root)):
        for name in folders + files:
            path = Path(folder) / name
            key = path.relative_to(root).as_posix()
            info = path.lstat()
            if path.is_symlink():
                state[key] = ("link", os.readlink(str(path)))
            elif path.is_dir():
                state[key] = ("folder", info.st_mtime_ns)
            else:
                state[key] = ("file", info.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
    return state


def report(done):
    try:
        data = json.loads(done.stdout)
    except ValueError:
        raise AssertionError("new-device gave no JSON (exit {}):\n{}{}".format(
            done.returncode, done.stdout, done.stderr))
    data["rows"] = {row["layer"]: row for row in data["layers"]}
    return data


class Device:
    """A stand-in dev repository, a fresh clone of it, and each layer a device rebuilds."""

    def __init__(self, base, where=None, labs=False):
        self.base = base
        self.home = base / "home"
        self.home.mkdir(parents=True)
        self.upstream = base / "upstream" / "fake-tool"
        self.upstream.mkdir(parents=True)
        git(self.upstream, "init", "-q")
        write(self.upstream / "tool.txt", "pinned\n")
        self.pin = commit_all(self.upstream, "the pinned commit")
        write(self.upstream / "tool.txt", "newer\n")
        self.later = commit_all(self.upstream, "a commit past the pin")
        self.clones = ["Harness/fake-tool"]
        if labs:
            self.clones += ["Harness/learn-claude-code"]
        github = base / "github" / "dev"
        github.mkdir(parents=True)
        git(github, "init", "-q")
        write(github / "Harness" / "repos.txt", "# path<TAB>url<TAB>pinned-commit\n#\n" + "".join(
            "{}\thttps://example.invalid/{}.git\t{}\n".format(path, path.split("/")[-1], self.pin)
            for path in self.clones))
        shutil.copy2(str(SOURCE / "Harness" / "bootstrap.sh"), str(github / "Harness" / "bootstrap.sh"))
        shutil.copy2(str(SOURCE / "Harness" / "separate-projects.txt"), str(github / "Harness" / "separate-projects.txt"))
        write(github / "Harness" / "setup-reverse.py", REVERSE)
        write(github / "Harness" / "knowledge-tools-sync.py", KNOWLEDGE)
        shutil.copy2(str(SOURCE / "Harness" / "library.py"), str(github / "Harness" / "library.py"))
        write(github / ".claude" / "skills" / "own" / "SKILL.md", "---\nname: own\n---\n")
        for name in ("claude-start", "start-check"):
            write(github / "Harness" / "bin" / name, "#!/bin/sh\n")
        if where is not None:
            write(github / "Harness" / "bin" / "agent-memory", where)
        # Dated snapshots in Setup/handoff, when one was made; the newest wins, and the
        # restore steps live in NEW_DEVICE.md.
        write(github / "Setup" / "handoff" / "claude-memory-2026-09-01" / "MEMORY.md", "# older\n")
        write(github / "Setup" / "handoff" / "claude-memory-2026-09-20" / "originals.zip", "zip\n")
        write(github / "Setup" / "NEW_DEVICE.md", "# restore steps\n")
        ignored = ["Harness/.runtime", "Projects/Imported", ".claude/hooks/library"]
        write(github / ".gitignore", "".join("/{}/\n".format(path) for path in ignored + self.clones)
              + "/.claude/settings.local.json\n")
        commit_all(github, "dev as its remote holds it")
        self.dev = base / "device" / "dev with spaces"
        self.dev.parent.mkdir()
        git(base, "clone", "-q", str(github), str(self.dev))
        git(self.dev, "remote", "set-url", "origin", DEVARNESS_REMOTE)

    def rebuild_clones(self):
        for relative in self.clones:
            target = self.dev / relative
            git(self.base, "clone", "-q", str(self.upstream), str(target))
            git(target, "checkout", "-q", "--detach", self.pin)

    def rebuild_local_settings(self):
        write(self.dev / ".claude" / "settings.local.json", '{"enabledMcpjsonServers": ["n8n-mcp"]}\n')

    def rebuild_launchers(self):
        # bootstrap links every launcher whose source exists (its "launcher wrappers" loop), so a
        # fixture that installs a agent-memory stand-in must link that one too.
        for source in sorted((self.dev / "Harness" / "bin").iterdir()):
            symlink(source, self.home / ".local" / "bin" / source.name)

    def rebuild_reverse(self):
        write(self.dev / "Harness" / ".runtime" / "reverse-ready", "")

    def rebuild_system_layers(self):
        """What bootstrap's system steps leave: skill links, MCP servers, superpowers, markitdown,
        the knowledge tools and the library index."""
        for folder in (".claude", ".agents"):
            write(self.home / folder / "skills" / "own" / "SKILL.md", "---\nname: own\n---\n")
        write(self.home / ".claude.json", json.dumps({"mcpServers": {"laya": {}, "rea": {}}}))
        write(self.home / ".codex" / "config.toml", "[mcp_servers.laya]\ncommand = \"python3\"\n"
                                                   "[mcp_servers.rea]\ncommand = \"python3\"\n")
        write(self.home / ".claude" / "plugins" / "installed_plugins.json",
              json.dumps({"plugins": {"superpowers@claude-plugins-official": [{"scope": "user"}]}}))
        write(self.home / ".codex" / "plugins" / "cache" / "superpowers-dev" / "superpowers" / "abc"
              / ".codex-plugin" / "plugin.json", "{}\n")
        write(self.home / ".local" / "bin" / "markitdown", "")
        write(self.dev / "Harness" / ".runtime" / "knowledge-ready", "")
        write(self.dev / ".claude" / "hooks" / "library" / "index.json", HEALTHY_INDEX)

    def complete(self):
        self.rebuild_clones()
        self.rebuild_local_settings()
        self.rebuild_launchers()
        self.rebuild_reverse()
        self.rebuild_system_layers()
        return self

    def windows_settings(self):
        for key, value in (("core.autocrlf", "false"), ("core.eol", "lf"), ("core.symlinks", "true"),
                           ("core.longpaths", "true")):
            git(self.dev, "config", "--local", key, value)
        return self

    def add_separate_projects(self):
        for line in (self.dev / "Harness/separate-projects.txt").read_text().splitlines():
            name = line.strip()
            if name and not name.startswith("#"):
                (self.dev / name).mkdir(parents=True, exist_ok=True)

    def install_labs(self):
        runtime = self.dev / "Harness" / ".runtime"
        write(runtime / "learn-claude-code" / self.pin / "installation.json", '{"status": "prepared"}\n')

    def memory_folder(self):
        return self.home / ".claude" / "projects" / "-device-dev" / "memory"

    def check(self, platform="macos", as_json=True, env=None, dev=None, timeout=120):
        command = [sys.executable, str(TOOL), "check", "--root", str(dev or self.dev), "--home", str(self.home)]
        if as_json:
            command.append("--json")
        run_env = dict(ENV)
        run_env["DEVARNESS_NEWDEVICE_PLATFORM"] = platform
        run_env.update(env or {})
        return subprocess.run(command, capture_output=True, encoding="utf-8", env=run_env, timeout=timeout)


class Case(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="new-device-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()

    def make(self, name="one", where=None, labs=False):
        return Device(self.base / name, where=where, labs=labs)

    def only_missing(self, done, layer):
        data = report(done)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual([name for name in LAYERS if data["rows"][name]["status"] == "missing"], [layer])
        self.assertEqual(data["verdict"], "NEW DEVICE INCOMPLETE " + DASH + " 1 required layer missing")
        return data["rows"][layer]


class RequiredLayerTests(Case):
    def setUp(self):
        super().setUp()
        self.device = self.make()

    def test_a_complete_device_is_ready_and_exits_zero(self):
        done = self.device.complete().check()
        data = report(done)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(data["verdict"], "NEW DEVICE READY")
        self.assertEqual([row["layer"] for row in data["layers"]], LAYERS)
        for name in REQUIRED:
            self.assertEqual((data["rows"][name]["status"], data["rows"][name]["fix"]), ("ok", ""), data["rows"][name])
        self.assertEqual(data["rows"]["git-settings"]["status"], "n/a")

    def test_a_fresh_clone_with_nothing_rebuilt_names_every_missing_required_layer_and_its_fix(self):
        done = self.device.check()
        data = report(done)
        rows = data["rows"]
        self.assertEqual(done.returncode, 1)
        self.assertEqual([name for name in LAYERS if rows[name]["status"] == "missing"],
                         ["vendored-clones", "local-settings", "launchers"] + SYSTEM_LAYERS)
        self.assertEqual(rows["checkout"]["status"], "ok")
        self.assertEqual(data["verdict"], "NEW DEVICE INCOMPLETE " + DASH + " 9 required layers missing")
        for name in ("vendored-clones", "local-settings", "launchers"):
            self.assertEqual(rows[name]["fix"], BOOTSTRAP, rows[name])
        self.assertIn("Harness/fake-tool", rows["vendored-clones"]["detail"])
        # bootstrap links only the launchers whose source exists (Harness/bootstrap.sh:130)
        self.assertIn("claude-start", rows["launchers"]["detail"])
        self.assertIn("start-check", rows["launchers"]["detail"])
        self.assertNotIn("md-format", rows["launchers"]["detail"])

    def test_a_folder_that_is_not_a_dev_clone_misses_every_required_layer_and_is_told_to_clone(self):
        downloaded = self.base / "downloaded"
        downloaded.mkdir()
        cases = (("a folder outside any repository", downloaded),
                 ("a folder inside a dev clone", self.device.dev / "Setup"))
        for label, folder in cases:
            with self.subTest(label):
                done = self.device.check(dev=folder)
                data = report(done)
                self.assertEqual(done.returncode, 1)
                self.assertEqual(data["rows"]["checkout"]["status"], "missing")
                self.assertEqual(data["rows"]["checkout"]["fix"], CLONE)
        done = self.device.check(dev=downloaded)
        self.assertEqual([name for name in LAYERS if report(done)["rows"][name]["status"] == "missing"], REQUIRED)

    def test_any_other_origin_is_shown_without_its_credential(self):
        self.device.complete()
        git(self.device.dev, "remote", "set-url", "origin",
            "https://someone:secret-token" + "@" + "github.com/someone/dev.git")   # split: not an email address
        done = self.device.check()
        row = report(done)["rows"]["checkout"]
        self.assertEqual((done.returncode, row["status"]), (0, "ok"), done.stdout)
        self.assertIn("github.com/someone/dev.git", row["detail"])
        self.assertNotIn("secret-token", row["detail"])

    def test_a_checkout_without_an_origin_is_a_note_and_the_device_is_still_ready(self):
        # dev starts life with no remote (design spec): the owner makes one later.
        self.device.complete()
        git(self.device.dev, "remote", "remove", "origin")
        done = self.device.check()
        data = report(done)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(data["verdict"], "NEW DEVICE READY")
        row = data["rows"]["checkout"]
        self.assertEqual(row["status"], "note")
        self.assertIn("no origin remote yet", row["detail"])
        self.assertIn("git remote add origin", row["fix"])

    def test_uncommitted_changes_are_a_note_and_do_not_fail_the_checkout(self):
        self.device.complete()
        write(self.device.dev / "Setup" / "draft.md", "not committed\n")
        done = self.device.check()
        row = report(done)["rows"]["checkout"]
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(row["status"], "note")
        self.assertIn("1 uncommitted", row["detail"])

    def test_an_absent_vendored_clone_is_listed_and_bootstrap_clones_it(self):
        self.device.complete()
        clone = self.device.dev / "Harness" / "fake-tool"
        remove_tree(clone)
        with self.subTest("absent"):
            row = self.only_missing(self.device.check(), "vendored-clones")
            self.assertIn("Harness/fake-tool", row["detail"])
            self.assertEqual(row["fix"], BOOTSTRAP)
        # An empty folder is what a gitlink leaves; git run inside it reads dev's own HEAD.
        clone.mkdir()
        with self.subTest("an empty folder inside dev"):
            row = self.only_missing(self.device.check(), "vendored-clones")
            self.assertIn("Harness/fake-tool", row["detail"])
            self.assertEqual(row["fix"], BOOTSTRAP)

    def test_a_vendored_clone_off_its_pin_is_listed_with_the_run_that_restores_it(self):
        self.device.complete()
        git(self.device.dev / "Harness" / "fake-tool", "checkout", "-q", "--detach", self.device.later)
        row = self.only_missing(self.device.check(), "vendored-clones")
        self.assertIn("Harness/fake-tool", row["detail"])
        self.assertEqual(row["fix"], 'Harness/bin/update-tools apply --budget 1800 --only "Harness/fake-tool"')

    def test_absent_local_settings_are_missing_and_bootstrap_writes_them(self):
        self.device.complete()
        os.remove(str(self.device.dev / ".claude" / "settings.local.json"))
        row = self.only_missing(self.device.check(), "local-settings")
        self.assertEqual(row["fix"], BOOTSTRAP)

    def test_local_settings_that_do_not_parse_are_missing_and_moved_aside_for_bootstrap(self):
        self.device.complete()
        write(self.device.dev / ".claude" / "settings.local.json", '{"enabledMcpjsonServers": [\n')
        row = self.only_missing(self.device.check(), "local-settings")
        self.assertIn(".claude/settings.local.json", row["fix"])
        self.assertTrue(row["fix"].endswith("; " + BOOTSTRAP), row)

    def test_an_absent_launcher_link_is_missing_and_bootstrap_links_it(self):
        self.device.complete()
        os.remove(str(self.device.home / ".local" / "bin" / "start-check"))
        row = self.only_missing(self.device.check(), "launchers")
        self.assertIn("start-check", row["detail"])
        self.assertNotIn("claude-start", row["detail"])
        self.assertEqual(row["fix"], BOOTSTRAP)

    def test_a_launcher_that_does_not_resolve_into_this_checkout_is_missing(self):
        # The old workspace's launchers on the same machine are the case that matters.
        self.device.complete()
        link = self.device.home / ".local" / "bin" / "claude-start"
        other = write(self.base / "the old workspace" / "Harness" / "bin" / "claude-start", "#!/bin/sh\n")
        with self.subTest("a link into another checkout"):
            os.remove(str(link))
            symlink(other, link)
            self.assertIn("claude-start", self.only_missing(self.device.check(), "launchers")["detail"])
        with self.subTest("a copy, as Git Bash makes without native symlinks"):
            os.remove(str(link))
            shutil.copy2(str(self.device.dev / "Harness" / "bin" / "claude-start"), str(link))
            self.assertIn("claude-start", self.only_missing(self.device.check(), "launchers")["detail"])

    def test_a_launcher_is_required_as_soon_as_its_source_exists_not_because_it_is_named_here(self):
        # agent-memory joined bootstrap's loop (79a4cfe) after this suite was written, and the tool
        # reads that loop so the two cannot drift; nothing else proves it reads the loop rather
        # than a list of its own.
        device = self.make("with-memory", where=WHERE).complete()
        os.remove(str(device.home / ".local" / "bin" / "agent-memory"))
        row = self.only_missing(device.check(), "launchers")
        self.assertIn("agent-memory (absent)", row["detail"])
        self.assertNotIn("claude-start", row["detail"])
        self.assertEqual(row["fix"], BOOTSTRAP)

    def test_the_layers_that_stayed_in_the_old_workspace_are_gone(self):
        rows = report(self.device.complete().check())["rows"]
        for name in ("pcb-studio", "device", "hindsight"):
            self.assertNotIn(name, rows)


class SystemLayerTests(Case):
    """The layers bootstrap's system steps install: READY said nothing of them (loop round 1)."""

    def setUp(self):
        super().setUp()
        self.device = self.make().complete()

    def test_each_layer_bootstrap_installs_is_required_and_named_with_its_fix(self):
        home, dev = self.device.home, self.device.dev
        cases = (("skill-links", home / ".agents" / "skills" / "own" / "SKILL.md", "~/.agents/skills/own"),
                 ("mcp-servers", home / ".codex" / "config.toml", "laya for Codex"),
                 ("superpowers", home / ".claude" / "plugins" / "installed_plugins.json", "Claude Code"),
                 ("markitdown", home / ".local" / "bin" / "markitdown", "md-pages"),
                 ("knowledge-tools", dev / "Harness" / ".runtime" / "knowledge-ready", "diagram-design"),
                 ("library-index", dev / ".claude" / "hooks" / "library" / "index.json", "no usable index"))
        for name, path, said in cases:
            with self.subTest(name):
                kept = path.read_bytes()
                path.unlink()
                row = self.only_missing(self.device.check(), name)
                self.assertIn(said, row["detail"])
                self.assertTrue(row["fix"], row)
                path.write_bytes(kept)
        self.assertEqual(self.device.check().returncode, 0)

    def test_a_degraded_library_index_is_missing_and_a_stale_one_a_note(self):
        index = self.device.dev / ".claude" / "hooks" / "library" / "index.json"
        write(index, json.dumps(dict(json.loads(HEALTHY_INDEX), diagnostics=["a source failed"])))
        self.assertIn("1 diagnostic", self.only_missing(self.device.check(), "library-index")["detail"])
        gone = str(index.parent / "a-source-since-removed.json")
        write(index, json.dumps(dict(json.loads(HEALTHY_INDEX), fingerprints={gone: "file:0:0:0:x:"})))
        done = self.device.check()
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(report(done)["rows"]["library-index"]["status"], "note")

    def test_a_launcher_link_dev_no_longer_has_is_missing(self):
        symlink(self.device.dev / "Harness" / "bin" / "old-name", self.device.home / ".local" / "bin" / "old-name")
        row = self.only_missing(self.device.check(), "launchers")
        self.assertIn("old-name (dangling", row["detail"])
        self.assertEqual(row["fix"], BOOTSTRAP)

    def test_a_no_system_install_reports_the_system_only_layers_as_notes(self):
        home, dev = self.device.home, self.device.dev
        for path in (home / ".codex" / "config.toml", home / ".claude" / "plugins" / "installed_plugins.json",
                     home / ".local" / "bin" / "markitdown", dev / "Harness" / ".runtime" / "knowledge-ready"):
            path.unlink()
        system_only = ("mcp-servers", "superpowers", "markitdown", "knowledge-tools")
        self.assertEqual(self.device.check().returncode, 1)          # a real install still needs them
        for how, env in (("flag", None), ("env", {"DEVARNESS_NO_SYSTEM": "1"})):
            with self.subTest(how):
                command = [sys.executable, str(TOOL), "check", "--root", str(dev), "--home", str(home), "--json"]
                if how == "flag":
                    command.append("--no-system")
                run_env = dict(ENV, DEVARNESS_NEWDEVICE_PLATFORM="macos", **(env or {}))
                done = subprocess.run(command, capture_output=True, encoding="utf-8", env=run_env, timeout=120)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                rows = report(done)["rows"]
                for name in system_only:
                    self.assertEqual(rows[name]["status"], "note", name)
                    self.assertIn("--no-system", rows[name]["detail"])
        command = [sys.executable, str(TOOL), "check", "--root", str(dev), "--home", str(home), "--json"]
        done = subprocess.run(command, capture_output=True, encoding="utf-8", timeout=120,
                              env=dict(ENV, DEVARNESS_NEWDEVICE_PLATFORM="macos", DEVARNESS_NO_SYSTEM="0"))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)   # "0" is not true

    def test_the_client_layers_that_need_a_login_or_a_licence_are_optional(self):
        rows = report(self.device.check())["rows"]
        for name in ("laya", "statusline-tools", "pi"):
            self.assertFalse(rows[name]["required"], name)


class WindowsTests(Case):
    def test_git_settings_are_not_applicable_off_windows_and_required_on_windows(self):
        device = self.make().complete()
        done = device.check(platform="macos")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(report(done)["rows"]["git-settings"]["status"], "n/a")
        row = self.only_missing(device.check(platform="windows"), "git-settings")
        self.assertIn("core.symlinks", row["detail"])
        done = device.windows_settings().check(platform="windows")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(report(done)["rows"]["git-settings"]["status"], "ok")

    def test_on_windows_a_wrong_git_setting_is_missing_and_the_clone_is_made_again_with_all_four(self):
        device = self.make().complete().windows_settings()
        git(device.dev, "config", "--local", "core.autocrlf", "true")
        row = self.only_missing(device.check(platform="windows"), "git-settings")
        self.assertIn("core.autocrlf", row["detail"])
        self.assertEqual(row["fix"], "mv ~/dev ~/dev-bad-clone; " + WINDOWS_CLONE)

    def test_on_windows_the_fixes_ask_for_native_symlinks_and_the_four_settings(self):
        device = self.make().windows_settings()
        rows = report(device.check(platform="windows"))["rows"]
        for name in ("vendored-clones", "local-settings", "launchers"):
            self.assertEqual(rows[name]["fix"], WINDOWS_BOOTSTRAP, rows[name])
        downloaded = self.base / "downloaded"
        downloaded.mkdir()
        rows = report(device.check(platform="windows", dev=downloaded))["rows"]
        self.assertEqual(rows["checkout"]["fix"], WINDOWS_CLONE)
        self.assertEqual((rows["git-settings"]["status"], rows["git-settings"]["fix"]), ("missing", WINDOWS_CLONE))


class OptionalLayerTests(Case):
    def test_optional_layers_never_change_the_exit_code(self):
        bare = self.make("bare").complete()
        write(bare.dev / "Harness" / "separate-projects.txt", "Elsewhere\n")
        done = bare.check()
        self.assertEqual(done.returncode, 0, done.stdout)
        for name in ("separate-projects", "labs", "memory"):
            self.assertEqual(report(done)["rows"][name]["status"], "note", name)
        full = self.make("full", where=WHERE, labs=True).complete()
        full.add_separate_projects()
        full.install_labs()
        full.memory_folder().mkdir(parents=True)
        done = full.check()
        self.assertEqual(done.returncode, 0, done.stdout)
        for name in ("separate-projects", "labs", "memory"):
            self.assertEqual(report(done)["rows"][name]["status"], "ok", name)
        os.remove(str(full.dev / ".claude" / "settings.local.json"))
        self.assertEqual(full.check().returncode, 1)
        broken = self.make("broken", where=BROKEN_WHERE).complete()
        done = broken.check()
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(report(done)["rows"]["memory"]["status"], "note")

    def test_separate_projects_are_present_or_absent_and_never_missing(self):
        device = self.make().complete()
        # This fixture tests presence reporting, not the live project inventory.
        write(device.dev / "Harness" / "separate-projects.txt",
              "DEMO_FIRMWARE\nDEMO_DATA\nSample Lessons\nSample Studies\nProjects/DEMO_SENSOR_LAB\n")
        (device.dev / "DEMO_FIRMWARE").mkdir()
        (device.dev / "Projects" / "DEMO_SENSOR_LAB").mkdir(parents=True)
        done = device.check()
        row = report(done)["rows"]["separate-projects"]
        self.assertEqual(done.returncode, 0)
        self.assertEqual((row["status"], row["detail"], row["fix"]),
                         ("note", "present: DEMO_FIRMWARE, Projects/DEMO_SENSOR_LAB; absent: DEMO_DATA, Sample Lessons, Sample Studies", ""))
        (device.dev / "DEMO_DATA").mkdir()
        (device.dev / "Sample Lessons").mkdir()
        (device.dev / "Sample Studies").mkdir()
        row = report(device.check())["rows"]["separate-projects"]
        self.assertEqual(row["status"], "ok")

    def test_a_list_of_comments_alone_is_none_listed(self):
        device = self.make().complete()
        write(device.dev / "Harness" / "separate-projects.txt", "# the owner's projects\n")
        row = report(device.check())["rows"]["separate-projects"]
        self.assertEqual((row["status"], row["detail"], row["fix"]), ("ok", "none listed", ""))

    def test_separate_projects_come_from_the_shared_list_not_a_copy_in_the_tool(self):
        device = self.make().complete()
        write(device.dev / "Harness" / "separate-projects.txt", "# the owner's projects\nElsewhere\nNested/Project\n")
        (device.dev / "Nested" / "Project").mkdir(parents=True)
        row = report(device.check())["rows"]["separate-projects"]
        self.assertEqual((row["status"], row["detail"]), ("note", "present: Nested/Project; absent: Elsewhere"))
        (device.dev / "Harness" / "separate-projects.txt").unlink()
        row = report(device.check())["rows"]["separate-projects"]
        self.assertEqual((row["status"], row["detail"]), ("note", "Harness/separate-projects.txt cannot be read"))

    def test_labs_report_each_installed_runtime_and_the_install_command_for_the_rest(self):
        device = self.make(labs=True).complete()
        runtime = device.dev / "Harness" / ".runtime"
        write(runtime / "learn-claude-code" / ("0" * 40) / "installation.json", "{}\n")
        row = report(device.check())["rows"]["labs"]
        self.assertEqual(row["status"], "note")
        self.assertIn("not installed: learn-claude-code", row["detail"])     # installed at another pin
        self.assertEqual(row["fix"], "python3 Harness/setup-learn-claude.py --install")
        device.install_labs()
        remove_tree(runtime / "learn-claude-code")
        with self.subTest("learn-claude-code is POSIX-only (Harness/setup-learn-claude.py:66-67)"):
            row = report(device.check(platform="windows"))["rows"]["labs"]
            self.assertEqual((row["status"], row["fix"]), ("ok", ""))
        device.install_labs()
        row = report(device.check())["rows"]["labs"]
        self.assertEqual((row["status"], row["fix"]), ("ok", ""))

    def test_memory_without_agent_memory_is_a_note_that_it_is_not_installed(self):
        row = report(self.make().complete().check())["rows"]["memory"]
        self.assertEqual((row["status"], row["detail"]), ("note", "agent-memory not installed"))

    def test_an_absent_memory_folder_names_the_newest_handoff_snapshot_and_its_restore_steps(self):
        device = self.make(where=WHERE).complete()
        done = device.check()
        row = report(done)["rows"]["memory"]
        self.assertEqual(done.returncode, 0)
        self.assertEqual(row["status"], "note")
        self.assertIn(str(device.memory_folder()), row["detail"])
        self.assertIn("Setup/handoff/claude-memory-2026-09-20/originals.zip", row["fix"])
        self.assertNotIn("2026-09-01", row["fix"])
        self.assertIn("Setup/NEW_DEVICE.md", row["fix"])
        device.memory_folder().mkdir(parents=True)
        row = report(device.check())["rows"]["memory"]
        self.assertEqual((row["status"], row["fix"]), ("ok", ""))

    def test_the_daily_run_is_a_note_with_its_fix_until_it_is_registered(self):
        device = self.make().complete()
        done = device.check(platform="macos")
        row = report(done)["rows"]["daily-run"]
        self.assertEqual(done.returncode, 0)
        self.assertEqual((row["required"], row["status"], row["fix"]),
                         (False, "note", "Harness/bin/update-tools install-daily"))
        self.assertIn("last long run never", row["detail"])
        # The shared scheduler writes the plist under the task's expected name.
        write(device.home / "Harness" / "LaunchAgents" / "DEVARNESS_update_daily.plist", "<plist/>\n")
        write(device.dev / ".claude" / "hooks" / "update-tools.state",
              json.dumps({"last_long_run": time.time() - 3 * 3600}))
        row = report(device.check(platform="macos"))["rows"]["daily-run"]
        self.assertEqual((row["status"], row["fix"]), ("ok", ""))
        self.assertIn("last long run 3 h ago", row["detail"])


class PersonalAndReverseTests(Case):
    def test_the_owners_personal_clones_are_checked_from_the_given_home(self):
        # The book PDFs' pin lives in ~/.config/devarness/personal-repos.txt, never in git.
        device = self.make().complete()
        write(device.home / ".config" / "devarness" / "personal-repos.txt",
              "# mine\nHarness/private\thttps://example.invalid/private.git\t{}\n".format(device.pin))
        row = self.only_missing(device.check(), "vendored-clones")
        self.assertIn("1 of 2 not at their pin: Harness/private (absent)", row["detail"])
        self.assertEqual(row["fix"], BOOTSTRAP)
        git(device.base, "clone", "-q", str(device.upstream), str(device.dev / "Harness" / "private"))
        git(device.dev / "Harness" / "private", "checkout", "-q", "--detach", device.pin)
        done = device.check()
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(report(done)["rows"]["vendored-clones"]["detail"], "all 2 at their pins")

    def test_the_reverse_runtimes_are_required_on_windows_and_not_applicable_elsewhere(self):
        device = self.make().complete().windows_settings()
        (device.dev / "Harness" / ".runtime" / "reverse-ready").unlink()
        row = self.only_missing(device.check(platform="windows"), "reverse-tools")
        self.assertEqual(row["detail"], "not installed: jdk, rea")
        self.assertEqual(row["fix"], "python Harness/setup-reverse.py --from <the USB's reverse folder>")
        self.assertEqual(report(device.check(platform="macos"))["rows"]["reverse-tools"]["status"], "n/a")
        device.rebuild_reverse()
        done = device.check(platform="windows")
        self.assertEqual((done.returncode, report(done)["rows"]["reverse-tools"]["status"]), (0, "ok"), done.stdout)

    def test_notify_reads_its_topic_from_the_dev_config_folder(self):
        device = self.make().complete()
        env = {"DEVARNESS_NTFY_TOPIC": ""}
        self.assertEqual(report(device.check(env=env))["rows"]["notify"]["status"], "note")
        write(device.home / ".config" / "devarness" / "ntfy-topic", "a-topic\n")
        self.assertEqual(report(device.check(env=env))["rows"]["notify"]["status"], "ok")


class ContractTests(Case):
    def test_the_text_table_carries_the_same_layers_fixes_and_verdict_as_json(self):
        device = self.make(where=WHERE)
        data = report(device.check())
        done = device.check(as_json=False)
        self.assertEqual(done.returncode, 1)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[-1], data["verdict"])
        for row in data["layers"]:
            at = [index for index, line in enumerate(lines) if line.split()[:1] == [row["layer"]]]
            self.assertEqual(len(at), 1, row["layer"])
            fields = lines[at[0]].split(None, 3)
            self.assertEqual(fields[1:3], ["yes" if row["required"] else "no", row["status"]])
            self.assertEqual(fields[3], row["detail"])
            following = lines[at[0] + 1].strip()
            if row["fix"]:
                self.assertEqual(following, "fix: " + row["fix"])
            else:
                self.assertFalse(following.startswith("fix:"), row["layer"])

    def test_the_check_writes_nothing_in_the_clones_or_the_home(self):
        device = self.make(where=WHERE, labs=True).complete()
        device.add_separate_projects()
        device.install_labs()
        # A tracked file whose time no longer matches the index: a git status
        # allowed to take optional locks rewrites .git/index to record it.
        later = time.time() + 3600
        os.utime(str(device.dev / "Harness" / "repos.txt"), (later, later))
        before = snapshot(self.base)
        for platform in ("macos", "windows"):
            for as_json in (True, False):
                device.check(platform=platform, as_json=as_json)
        after = snapshot(self.base)
        self.assertEqual(sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key)), [])

    def test_the_check_never_contacts_a_remote(self):
        device = self.make(where=WHERE).complete()
        probe = self.base / "probe"
        marker = probe / "contacted"
        ssh = write(probe / "ssh.py", "import pathlib, sys\n"
                    "pathlib.Path(sys.argv[0]).with_name('contacted').write_text(' '.join(sys.argv[1:]))\n"
                    "sys.exit(255)\n")
        write(probe / "guard" / "sitecustomize.py", GUARD.format(marker=str(marker)))
        env = {"GIT_SSH_COMMAND": '"{}" "{}"'.format(sys.executable, ssh), "PYTHONPATH": str(probe / "guard")}
        # The probe itself must notice a contact, or its silence proves nothing.
        subprocess.run(["git", "-C", str(device.dev), "ls-remote", "origin"], capture_output=True,
                       env=dict(ENV, **env), timeout=60)
        self.assertTrue(marker.exists(), "the stand-in ssh was never called")
        marker.unlink()
        for platform in ("macos", "windows"):
            report(device.check(platform=platform, env=env))
        self.assertFalse(marker.exists(), marker.read_text() if marker.exists() else "")

    @unittest.skipIf(os.name == "nt", "the stand-in git is a POSIX shell script")
    def test_a_git_or_agent_memory_that_never_answers_is_cut_off_by_the_timeout(self):
        device = self.make(where=SILENT_WHERE).complete()
        real = shutil.which("git", path=ENV.get("PATH"))
        shim = write(self.base / "shim" / "git", "#!/bin/sh\n"
                     'for arg in "$@"; do\n  [ "$arg" = status ] && exec sleep 60\ndone\n'
                     "exec '{}' \"$@\"\n".format(real))
        shim.chmod(0o755)
        # The budget covers every git call, so it is kept well above what an
        # ordinary call takes on a busy machine; unbounded, this run takes 120 s.
        env = {"PATH": str(shim.parent) + os.pathsep + ENV.get("PATH", ""), "DEVARNESS_NEWDEVICE_TIMEOUT": "5"}
        started = time.monotonic()
        done = device.check(env=env, timeout=90)
        elapsed = time.monotonic() - started
        rows = report(done)["rows"]
        self.assertLess(elapsed, 45, done.stdout)
        for name in ("checkout", "memory"):
            self.assertEqual(rows[name]["status"], "note", done.stdout)
            self.assertIn("timed out", rows[name]["detail"], done.stdout)

    def test_usage_errors_exit_two(self):
        cases = ([], ["check", "--bogus"], ["check", "--root", str(self.base / "no such folder")])
        for args in cases:
            with self.subTest(args=args):
                done = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, encoding="utf-8",
                                      env=ENV, timeout=60)
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                # Python exits 2 too when it cannot open the script; the message says who refused.
                self.assertTrue(done.stderr.startswith(("usage: new-device", "new-device: ")), done.stderr)


if __name__ == "__main__":
    unittest.main()
