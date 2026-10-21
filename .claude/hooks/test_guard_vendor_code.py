#!/usr/bin/env python3
"""The vendor-code guard blocks reading a vendor application's packaged code, and nothing else.

Run: python3 .claude/hooks/test_guard_vendor_code.py

On 2026-09-22 a research sub-agent (claude-fable-5-1, general-purpose) was sent
to verify Obsidian facts, read-only, from named public sources. Two questions
asked for settings the docs do not name, and it fetched Obsidian's update
bundle, unpacked it and read the minified code, which Obsidian's terms forbid.
The blocked cases below are the commands it ran, shortened; the allowed cases
are the legitimate work that sits next to them — installing Obsidian from its
installer, reading the settings it writes into the owner's own vault.
"""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

HOOKS = Path(__file__).resolve().parent
RELEASE = "https://github.com/obsidianmd/obsidian-releases/releases/download/v1.13.7/"


def load():
    loader = importlib.machinery.SourceFileLoader("guard_vendor_code", str(HOOKS / "guard_vendor_code.py"))
    spec = importlib.util.spec_from_loader("guard_vendor_code", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


BLOCKED = {
    "the incident's download": (
        "Bash", {"command": 'cd /tmp/obs && curl -sS -L -m 120 -o obsidian-1.13.7.asar.gz "'
                            + RELEASE + 'obsidian-1.13.7.asar.gz"'}),
    "the incident's read, inside a heredoc": (
        "Bash", {"command": "cd /tmp/obs && python3 - <<'EOF'\nimport re\n"
                            "b=open('obsidian-1.13.7.asar','rb').read()\nEOF"}),
    "decompressing the bundle": ("Bash", {"command": "gunzip obsidian-1.13.7.asar.gz"}),
    "the asar tool extracting": ("Bash", {"command": "npx --yes @electron/asar extract app.asar out/"}),
    "the asar tool listing": ("Bash", {"command": "asar list resources/app.asar"}),
    "reading an installed app's archive": (
        "Bash", {"command": "strings Obsidian.app/Contents/Resources/obsidian.asar | head"}),
    "copying out of a mounted installer": (
        "Bash", {"command": "cp /Volumes/Obsidian/Obsidian.app/Contents/Resources/app.asar ."}),
    "the unpacked side folder": ("Bash", {"command": "ls Resources/app.asar.unpacked/node_modules"}),
    "PowerShell on the Windows PC": (
        "PowerShell", {"command": "Invoke-WebRequest -Uri " + RELEASE
                                  + "obsidian-1.13.7.asar.gz -OutFile o.asar.gz"}),
    "a web fetch of the bundle": ("WebFetch", {"url": RELEASE + "obsidian-1.13.7.asar.gz",
                                               "prompt": "list the config keys"}),
    "upper case does not hide it": ("Bash", {"command": "cat APP.ASAR"}),
    "reading the bundle's binary, no .asar in sight": (
        "Bash", {"command": "strings Obsidian.app/Contents/MacOS/Obsidian | grep -i newlinkformat"}),
    "prising open a Windows installer": (
        "Bash", {"command": "7z x Obsidian-1.13.7.exe -oout/"}),
    "a text command is no way round it": (
        "Bash", {"command": "git log -1 && curl -sSLO " + RELEASE + "obsidian-1.13.7.asar.gz"}),
}

ALLOWED = {
    "installing from the official disk image": (
        "Bash", {"command": "curl -L -o Obsidian-1.13.7.dmg " + RELEASE + "Obsidian-1.13.7.dmg"}),
    # Installing on a Mac IS copying the whole bundle out of a mounted image. The
    # first guard refused it, which would have blocked B0's own first step: the
    # bundle root is not its innards. Found by running the install, 2026-09-22.
    "mounting the image": (
        "Bash", {"command": 'hdiutil attach -nobrowse -quiet /tmp/Obsidian-1.13.7.dmg'}),
    "copying the whole bundle in": (
        "Bash", {"command": 'cp -R "/Volumes/Obsidian 1.13.7/Obsidian.app" /Applications/'}),
    "copying it with the trailing slash": (
        "Bash", {"command": 'cp -R "/Volumes/Obsidian 1.13.7/Obsidian.app/" /Applications/Obsidian.app/'}),
    "moving a bundle about": (
        "Bash", {"command": 'mv ~/Downloads/Obsidian.app /Applications/Obsidian.app'}),
    "unmounting afterwards": (
        "Bash", {"command": 'hdiutil detach "/Volumes/Obsidian 1.13.7"'}),
    "launching it": ("Bash", {"command": "open -a Obsidian"}),
    "asking the app its version": (
        "Bash", {"command": "defaults read /Applications/Obsidian.app/Contents/Info.plist "
                            "CFBundleShortVersionString"}),
    "installing on Windows": ("PowerShell", {"command": "winget install Obsidian.Obsidian"}),
    "reading the settings it writes into the vault": ("Bash", {"command": "cat .obsidian/app.json"}),
    "the per-device settings folder": ("Bash", {"command": "ls ~/Library/Application\\ Support/obsidian"}),
    "the word on its own": ("Bash", {"command": "echo 'asar is an archive format'"}),
    "a word that merely contains it": ("Bash", {"command": "grep -rn basar ."}),
    "a longer extension": ("Bash", {"command": "ls notes.asarx"}),
    "a commit message about the rule": (
        "Bash", {"command": "git commit -m 'Block reading a vendor application archive'"}),
    # The guard blocked the commit that fixed the guard, because the message
    # named the file type. A rule that stops you writing about itself is a
    # defect: git and echo move text, they do not open a package. 2026-09-22.
    "a commit message that names the file type": (
        "Bash", {"command": "git commit -m 'A .asar still blocks on its own'"}),
    "a commit message in a heredoc": (
        "Bash", {"command": "git commit -q -F - <<'EOF'\nGuard the .asar bundle\n\nBody.\nEOF"}),
    "searching the history for it": ("Bash", {"command": "git log --grep='app.asar'"}),
    "printing the rule": ("Bash", {"command": "echo 'nothing fetches a .asar here'"}),
    "the docs page for the format": ("WebFetch", {"url": "https://github.com/electron/asar",
                                                  "prompt": "what is it"}),
    "an ordinary edit": ("Edit", {"file_path": "app.asar.md", "old_string": "a", "new_string": "b"}),
}


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.guard = load()

    def test_every_step_of_the_incident_is_refused(self):
        for label, (tool, given) in BLOCKED.items():
            with self.subTest(label):
                self.assertIsNotNone(self.guard.verdict(tool, given), label + " was let through")

    def test_the_work_beside_it_is_left_alone(self):
        for label, (tool, given) in ALLOWED.items():
            with self.subTest(label):
                self.assertIsNone(self.guard.verdict(tool, given), label + " was refused")

    def test_the_refusal_names_the_rule_the_way_through_and_the_model(self):
        said = self.guard.verdict(*BLOCKED["the incident's download"])
        for part in ("not checked", "Claude/REMINDERS.md", "claude-fable-5-1", "the owner"):
            with self.subTest(part):
                self.assertIn(part, said)


class HookTests(unittest.TestCase):
    """The script as the harness runs it: JSON on stdin, exit 2 and stderr to refuse."""

    def run_hook(self, raw):
        return subprocess.run([sys.executable, str(HOOKS / "guard_vendor_code.py")], input=raw,
                              capture_output=True, text=True, timeout=30)

    def event(self, tool, given):
        return json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": given})

    def test_a_refusal_exits_2_and_says_why_on_stderr(self):
        done = self.run_hook(self.event(*BLOCKED["the incident's download"]))
        self.assertEqual(done.returncode, 2)
        self.assertIn("Blocked", done.stderr)
        self.assertEqual(done.stdout, "")

    def test_an_allowed_call_exits_0_and_says_nothing(self):
        done = self.run_hook(self.event(*ALLOWED["installing from the official disk image"]))
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))

    def test_anything_it_cannot_read_lets_the_call_through(self):
        for raw in ("", "not json", "null", "[]", json.dumps({"tool_input": None}),
                    json.dumps({"tool_name": "Bash", "tool_input": {"command": 7}})):
            with self.subTest(raw[:16]):
                self.assertEqual(self.run_hook(raw).returncode, 0)


class RegistrationTests(unittest.TestCase):
    """A guard that is written but not registered guards nothing."""

    def test_the_project_settings_run_it_on_every_tool_it_reads(self):
        settings = json.loads((HOOKS.parent / "settings.json").read_text(encoding="utf-8"))
        groups = [group for group in settings["hooks"]["PreToolUse"]
                  if any("guard_vendor_code.py" in hook["command"] for hook in group["hooks"])]
        self.assertEqual(len(groups), 1, "register the Python guard once under PreToolUse")
        self.assertEqual(set(groups[0]["matcher"].split("|")), {"Bash", "PowerShell", "WebFetch"})


if __name__ == "__main__":
    unittest.main()
