"""Preflight inventory must not claim an unprobed provider or loaded tools."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / ".claude/hooks/preflight_report.py"


def report(script=REPORT, full=True, workspace=ROOT):
    args = ["installed", str(workspace), "24.13.1",
            "ready", "ready", "ready", "ready", "ready", "on PATH",
            "ready"]
    env = dict(os.environ)
    env.pop("DEVARNESS_START_ALL", None)
    if full:
        env["DEVARNESS_START_ALL"] = "1"
    result = subprocess.run([sys.executable, str(script), *args], env=env,
                            capture_output=True, encoding="utf-8",
                            errors="replace", timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


class InventoryClaimsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = report()

    def test_library_only_understand_checks_source_and_runtime_not_root_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            library = root / 'Library'
            library.mkdir()
            (library / 'repos.txt').write_text('Library/Understand-Anything\tfixture\tpin\n')
            (library / 'library-policy.json').write_text(json.dumps({
                'entries': {'dev:skill:understand': {'mode': 'library-only'}}}))
            plugin = library / '.runtime/understand-anything/pin/understand-anything-plugin'
            core = plugin / 'packages/core/dist/index.js'
            for path in (core, plugin / 'packages/viewer/dist/index.html',
                         library / 'Understand-Anything/understand-anything-plugin/skills/understand/SKILL.md'):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture')
            banner = report(workspace=root)['systemMessage']
            line = next(s for s in banner.splitlines() if s.strip().startswith('understand '))
            self.assertIn('prepared', line)
            core.unlink()
            banner = report(workspace=root)['systemMessage']
            line = next(s for s in banner.splitlines() if s.strip().startswith('understand '))
            self.assertIn('MISSING', line)

    def test_ecc_is_not_required_after_library_migration(self):
        rows = [line.split()[0] for line in self.output['systemMessage'].splitlines()
                if line.strip()]
        self.assertNotIn('ecc', rows)
        self.assertNotIn('ECC startup', self.output['systemMessage'])

    def test_enabled_ecc_override_is_reported_instead_of_hidden(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.claude').mkdir()
            (root / '.claude/settings.local.json').write_text(json.dumps({
                'enabledPlugins': {'ecc@ecc': True}}))
            banner = report(workspace=root)['systemMessage']
        self.assertIn('ECC remains enabled', banner)

    def test_disabling_process_owner_still_degrades(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.claude').mkdir()
            (root / '.claude/settings.json').write_text(json.dumps({
                'enabledPlugins': {'superpowers@claude-plugins-official': False}}))
            banner = report(workspace=root)['systemMessage']
        self.assertIn('superpowers not loaded', banner)

    def test_docker_inventory_does_not_guess_provider_or_health(self):
        line = next(line for line in self.output["systemMessage"].splitlines()
                    if line.strip().startswith("docker "))
        self.assertNotIn("orbstack", line.lower())
        self.assertIn("daemon health not verified", line)

    def test_removed_tools_are_not_reported(self):
        # n8n and herdr were removed on 2026-10-07; a row for either would be a
        # claim about a tool dev no longer has.
        rows = [line.split()[0] for line in self.output["systemMessage"].splitlines() if line.strip()]
        self.assertNotIn("n8n", rows)
        self.assertNotIn("herdr", rows)
        self.assertNotIn("localhost:5678", self.output["additionalContext"])

    def test_tools_that_stayed_behind_are_not_reported(self):
        # dev leaves Hindsight, the device sheet, the Example App layer and its
        # Konnect runtime in the old workspace (design spec, 2026-10-08).
        message = self.output["systemMessage"]
        rows = [line.split()[0] for line in message.splitlines() if line.strip()]
        for gone in ("hindsight", "device", "sync", "konnect", "Studio"):
            self.assertNotIn(gone, rows)
        for text in ("hindsight", "Device_SyncSheet", "Example_App", "PCB Tools"):
            self.assertNotIn(text, message)
        self.assertNotIn("Konnect", message + self.output["additionalContext"])

    def test_incomplete_skill_entry_is_named_in_banner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            skills = root / ".agents/skills"
            (skills / "stale").mkdir(parents=True)
            (skills / "good").mkdir()
            (skills / "good/SKILL.md").write_text("name: good\n")
            (root / ".claude/skills/stale-claude").mkdir(parents=True)
            banner = report(workspace=root)["systemMessage"]
        self.assertIn("Incomplete dev skill: .agents/skills/stale", banner)
        self.assertIn("Incomplete dev skill: .claude/skills/stale-claude", banner)
        self.assertNotIn("Incomplete dev skill: .agents/skills/good", banner)

    def test_a_link_to_a_missing_skill_reads_as_missing_not_unreadable(self):
        # A skill link whose clone is not restored yet, and on Windows a link
        # git made as a file link before its target existed: Python 3.12's
        # is_dir() raises PermissionError on that one, and the whole Codex
        # inventory read "UNREADABLE PermissionError" (device test, 2026-10-09).
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            skills = root / ".agents/skills"
            skills.mkdir(parents=True)
            os.symlink(str(root / "not-restored"), str(skills / "gone"), target_is_directory=True)
            os.symlink(os.path.join("..", "..", "restored"), str(skills / "early"))   # before its target
            (root / "restored").mkdir()
            (root / "restored/SKILL.md").write_text("name: restored\n")
            banner = report(workspace=root)["systemMessage"]
        self.assertIn("Incomplete dev skill: .agents/skills/gone — missing (link target not restored)", banner)
        self.assertNotIn("Codex inventory could not be read", banner)
        if os.name == "nt":
            self.assertIn("Incomplete dev skill: .agents/skills/early — a file link to a folder", banner)

    def test_summary_does_not_claim_all_tools_work(self):
        banner = report(full=False)["systemMessage"]
        self.assertNotIn("all ready", banner)
        # A real degraded installation bypasses condensation. Also reject the
        # old claim at its source so that branch cannot pass unexercised.
        source = REPORT.read_text(encoding="utf-8")
        self.assertNotIn("tools checked, all ready", source)
        self.assertIn("runtime health and client tool exposure are separate", source)

    @staticmethod
    def row(banner, name):
        return next(s for s in banner.splitlines() if s.strip().startswith(name + ' '))

    @staticmethod
    def library_workspace(root, index=None):
        for rel in ('Library/bin/library', 'Library/library-sources.json', 'Library/library-policy.json',
                    '.claude/skills/library/SKILL.md', '.agents/skills/library/SKILL.md'):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text('fixture')
        (root / 'Library/library.py').write_bytes((ROOT / 'Library/library.py').read_bytes())
        if index is not None:
            path = root / '.claude/hooks/library/index.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict({'schema': 2, 'fingerprints': {}, 'entries': [],
                                             'diagnostics': [], 'router': []}, **index)))

    def test_the_library_row_reports_the_index_not_the_files(self):
        # Without an index every prompt's picks are empty: 'prepared' hid that.
        for index, state, degrades in ((None, 'MISSING', True), ({'diagnostics': ['x']}, 'DEGRADED', True),
                                       ({'notes': ['a plugin waits']}, 'ready', False)):
            with self.subTest(state), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.library_workspace(root, index)
                banner = report(workspace=root)['systemMessage']
                self.assertIn(state, self.row(banner, 'library'))
                self.assertEqual('library refresh' in banner.partition('Degraded:')[2], degrades, banner)

    def test_fix_hints_work_from_any_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            banner = report(workspace=Path(folder))['systemMessage']
        for relative in ('python3 Library/', 'python Library/', 'run Library/', 'see Library/'):
            self.assertNotIn(relative, banner)

    @unittest.skipUnless(os.name == 'nt', 'the Windows row')
    def test_fds_on_windows_never_points_at_the_mac_installer(self):
        self.assertNotIn('fds-setup', self.row(self.output['systemMessage'], 'fds'))

    def test_context_does_not_assign_every_client_claude_identity(self):
        context = self.output["additionalContext"]
        self.assertNotIn("you are PETER", context)
        self.assertIn("active client's identity", context)


if __name__ == "__main__":
    unittest.main()
