"""Profile changes only owned specialist links and always leaves a recovery map."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

LIBRARY = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('library_profile', LIBRARY / 'library-profile.py')
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'Library/vendor/understand'
        self.source.mkdir(parents=True)
        (self.source / 'SKILL.md').write_text('---\nname: understand\ndescription: Graph code\n---\n')
        self.links = []
        for client in ('.claude', '.agents'):
            link = self.root / client / 'skills/understand'
            link.parent.mkdir(parents=True)
            link.symlink_to(self.source, target_is_directory=True)
            self.links.append(link)
        self.policy = {'entries': {'dev:skill:understand': {'mode': 'library-only'}}}

    def test_retired_ecc_restore_cannot_remove_interleaved_trust_settings(self):
        config = self.root / 'config.toml'
        original = ('# BEGIN compact ECC skills\n'
                    '[[skills.config]]\npath = "fixture/ecc/skill"\nenabled = false\n'
                    '[hooks.state.fixture]\ntrusted_hash = "fixture-hash"\n'
                    '[projects.fixture]\ntrust_level = "trusted"\n'
                    '# END compact ECC skills\n')
        config.write_text(original)
        result = subprocess.run(
            [sys.executable, str(LIBRARY / 'codex-skill-profile.py'), '--restore'],
            env=dict(os.environ, CODEX_HOME=str(self.root)),
            capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_text(), original)

    def test_apply_and_restore_are_idempotent(self):
        snap = self.mod.snapshot(self.root, self.policy)
        self.mod.apply_profile(self.root, self.policy, snap)
        self.mod.apply_profile(self.root, self.policy, snap)
        for link in self.links:
            self.assertFalse(link.is_symlink())
        self.mod.restore_profile(self.root, snap)
        self.mod.restore_profile(self.root, snap)
        for link in self.links:
            self.assertEqual(link.resolve(), self.source.resolve())

    def test_foreign_retarget_aborts_before_any_link_is_removed(self):
        snap = self.mod.snapshot(self.root, self.policy)
        self.links[1].unlink()
        foreign = self.root / 'foreign'
        foreign.mkdir()
        self.links[1].symlink_to(foreign, target_is_directory=True)
        with self.assertRaises((ValueError, RuntimeError)):
            self.mod.apply_profile(self.root, self.policy, snap)
        self.assertTrue(self.links[0].is_symlink())

    def test_real_directory_is_not_deleted(self):
        self.links[0].unlink()
        self.links[0].mkdir()
        (self.links[0] / 'keep.txt').write_text('owner data')
        with self.assertRaises((ValueError, RuntimeError)):
            self.mod.snapshot(self.root, self.policy)
        self.assertEqual((self.links[0] / 'keep.txt').read_text(), 'owner data')

    def test_restore_refuses_new_foreign_directory(self):
        snap = self.mod.snapshot(self.root, self.policy)
        self.mod.apply_profile(self.root, self.policy, snap)
        self.links[0].mkdir()
        with self.assertRaises((ValueError, RuntimeError)):
            self.mod.restore_profile(self.root, snap)
        self.assertTrue(self.links[0].is_dir())

    def test_apply_writes_snapshot_before_mutating(self):
        snap = self.mod.snapshot(self.root, self.policy)
        self.mod.apply_profile(self.root, self.policy, snap)
        receipt = self.root / '.claude/hooks/library/profile-backup.json'
        self.assertTrue(receipt.is_file())
        data = json.loads(receipt.read_text())
        self.assertEqual(data, snap)

    def test_alias_only_policy_entries_do_not_request_a_migration(self):
        self.policy['entries']['dev:skill:browser-docs'] = {'aliases': ['OCR']}
        snap = self.mod.snapshot(self.root, self.policy)
        self.assertEqual({e['name'] for e in snap['entries']}, {'understand'})

    def test_unknown_modes_are_rejected(self):
        self.policy['entries']['dev:skill:understand']['mode'] = 'magical'
        with self.assertRaises(ValueError):
            self.mod.snapshot(self.root, self.policy)

    def test_snapshot_must_cover_both_client_paths(self):
        snap = self.mod.snapshot(self.root, self.policy)
        snap['entries'].pop()
        with self.assertRaises(ValueError):
            self.mod.apply_profile(self.root, self.policy, snap)
        self.assertTrue(all(p.is_symlink() for p in self.links))

    def test_redirected_backup_parent_is_refused_before_writing(self):
        snap = self.mod.snapshot(self.root, self.policy)
        outside = self.root / 'outside'
        outside.mkdir()
        (self.root / '.claude/hooks').symlink_to(outside, target_is_directory=True)
        with self.assertRaises((ValueError, RuntimeError)):
            self.mod.apply_profile(self.root, self.policy, snap)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue(all(p.is_symlink() for p in self.links))

    def test_restore_recreates_missing_client_parent(self):
        snap = self.mod.snapshot(self.root, self.policy)
        self.mod.apply_profile(self.root, self.policy, snap)
        (self.root / '.agents/skills').rmdir()
        (self.root / '.agents').rmdir()
        self.mod.restore_profile(self.root, snap)
        self.assertTrue(all(p.is_symlink() for p in self.links))

    def test_non_library_only_modes_stay_discoverable(self):
        self.policy['entries']['dev:skill:understand']['mode'] = 'task-triggered'
        snap = self.mod.snapshot(self.root, self.policy)
        self.mod.apply_profile(self.root, self.policy, snap)
        self.assertTrue(all(p.is_symlink() for p in self.links))


if __name__ == '__main__':
    unittest.main()
