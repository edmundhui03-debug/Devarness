#!/usr/bin/env python3
"""knowledge-tools-sync replaces the skill links it made, and refuses the rest.

Run: python3 Harness/tests/test_knowledge_tools_link.py

update-tools's first real run on 2026-09-24 rolled Understand-Anything back:
the installer at the new pin refused to replace `.claude/skills/understand`,
a link it had itself made at the old pin. A link that resolves under Library is
the installer's own and may be replaced; anything else is still refused.
"""
import importlib.machinery
import importlib.util
import os
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "Harness"
TOOL = LIBRARY / "knowledge-tools-sync.py"


def load():
    loader = importlib.machinery.SourceFileLoader("knowledge_tools_sync", str(TOOL))
    spec = importlib.util.spec_from_loader("knowledge_tools_sync", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.temporary = tempfile.TemporaryDirectory(prefix="link-")
        self.root = Path(self.temporary.name).resolve()
        self.target = self.root / "skills" / "understand"
        self.new_source = self.root / "new-runtime" / "understand"
        self.new_source.mkdir(parents=True)
        (self.new_source / "SKILL.md").write_text("new\n", encoding="utf-8")
        try:
            probe = self.root / "probe"
            probe.symlink_to(self.new_source, target_is_directory=True)
            probe.unlink()
        except OSError:
            self.skipTest("this device cannot make symlinks")

    def tearDown(self):
        self.temporary.cleanup()

    def test_library_only_policy_affects_root_but_not_satellites(self):
        self.mod.ROOT = self.root
        folder = self.root / 'Harness'
        folder.mkdir()
        policy = {'entries': {'dev:skill:understand': {'mode': 'library-only'}}}
        (folder / 'library-policy.json').write_text(json.dumps(policy))
        self.assertNotIn('understand', self.mod.discovery_names(self.root))
        self.assertIn('diagram-design', self.mod.discovery_names(self.root))
        self.assertIn('understand', self.mod.discovery_names(self.root / 'project'))
        self.assertEqual(self.mod.discovery_names(self.root),
                         self.mod.discovery_names(self.root))

    def test_missing_root_policy_is_refused(self):
        self.mod.ROOT = self.root
        with self.assertRaises(ValueError):
            self.mod.discovery_names(self.root)
        self.assertIn('understand', self.mod.discovery_names(self.root / 'project'))

    def test_non_object_policy_entry_is_refused(self):
        self.mod.ROOT = self.root
        folder = self.root / 'Harness'
        folder.mkdir()
        (folder / 'library-policy.json').write_text(json.dumps({
            'entries': {'dev:skill:understand': []}}))
        with self.assertRaises(ValueError):
            self.mod.discovery_names(self.root)

    def test_invalid_profile_cannot_silently_restore_all_links(self):
        self.mod.ROOT = self.root
        folder = self.root / 'Harness'
        folder.mkdir()
        (folder / 'library-policy.json').write_text('not json')
        with self.assertRaises(ValueError):
            self.mod.discovery_names(self.root)

    def test_a_link_into_librarys_own_runtime_is_replaced(self):
        old = LIBRARY / ".runtime"
        old.mkdir(exist_ok=True)
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(old, target_is_directory=True)
        self.mod.link(self.new_source, self.target)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(self.target.resolve(), self.new_source.resolve())

    def test_a_link_into_a_runtime_that_is_itself_a_link_is_replaced(self):
        # A worktree run through linked_run.py has Harness/.runtime as a
        # junction to main's, so the installer's own link resolves outside
        # Library; it is still the installer's to replace.
        self.mod.LIBRARY = self.root / "Harness"
        elsewhere = self.root / "main-runtime"
        (elsewhere / "understand").mkdir(parents=True)
        self.mod.LIBRARY.mkdir()
        (self.mod.LIBRARY / ".runtime").symlink_to(elsewhere, target_is_directory=True)
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(self.mod.LIBRARY / ".runtime" / "understand", target_is_directory=True)
        self.mod.link(self.new_source, self.target)
        self.assertEqual(self.target.resolve(), self.new_source.resolve())

    def test_a_link_naming_a_revision_is_rewritten_to_name_the_alias(self):
        # Tracked links name the per-device alias `current`, so a pin move
        # changes no tracked file; one naming the revision resolves to the
        # same folder today and must still be rewritten (review I5, 2026-09-24).
        self.mod.LIBRARY = self.root
        alias = self.root / "current"
        alias.symlink_to(os.path.relpath(self.new_source, self.root), target_is_directory=True)
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(self.new_source, target_is_directory=True)
        self.mod.link(alias, self.target)
        self.assertEqual(os.path.normpath(os.readlink(self.target)),
                         os.path.normpath(os.path.relpath(alias, self.target.parent)))
        self.assertEqual((self.target / "SKILL.md").read_text(encoding="utf-8"), "new\n")

    def test_a_link_elsewhere_and_a_real_folder_are_still_refused(self):
        foreign = self.root / "foreign"
        foreign.mkdir()
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(foreign, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            self.mod.link(self.new_source, self.target)
        self.target.unlink()
        self.target.mkdir()
        with self.assertRaises(RuntimeError):
            self.mod.link(self.new_source, self.target)


if __name__ == "__main__":
    unittest.main()
