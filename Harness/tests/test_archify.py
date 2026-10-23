"""Portable launcher contracts, including failing installations and subprocesses."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'bin/archify'

class ArchifyTest(unittest.TestCase):
    def setUp(self):
        loader = importlib.machinery.SourceFileLoader('archify', str(SCRIPT))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.mod = importlib.util.module_from_spec(spec)
        loader.exec_module(self.mod)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'Harness').mkdir()
        (self.root / 'Harness/repos.txt').write_text('Harness/archify\thttps://example.invalid/repo\t'+'a'*40+'\n')

    def fixture(self):
        p = self.root / 'Harness/archify/archify'
        (p / 'bin').mkdir(parents=True)
        (p / 'bin/archify.mjs').write_text('')
        (p / 'SKILL.md').write_text('')

    def test_missing_clone_is_not_ready(self):
        self.assertTrue(self.mod.problems(self.root))

    def test_wrong_pin_is_not_ready(self):
        self.fixture()
        with patch.object(self.mod, 'revision', return_value='b'*40), patch.object(self.mod.shutil, 'which', return_value='/node'):
            self.assertIn('pin mismatch', ' '.join(self.mod.problems(self.root)))

    def test_missing_node_is_not_ready(self):
        self.fixture()
        with patch.object(self.mod, 'revision', return_value='a'*40), patch.object(self.mod.shutil, 'which', return_value=None):
            self.assertIn('Node.js', ' '.join(self.mod.problems(self.root)))

    def test_launch_preserves_failure_and_disables_update_network(self):
        self.fixture()
        with patch.object(self.mod, 'problems', return_value=[]), patch.object(self.mod.shutil, 'which', return_value='/node'), patch.object(self.mod.subprocess, 'call', return_value=7) as call:
            self.assertEqual(self.mod.launch(self.root, ['validate','workflow','file with spaces.json']), 7)
            args = call.call_args
            self.assertEqual(args.args[0][-1], 'file with spaces.json')
            self.assertEqual(args.kwargs['env']['ARCHIFY_UPDATE_CHECK_DISABLED'], '1')

    def test_install_refuses_existing_user_path(self):
        src = self.root / 'source'; src.mkdir()
        dst = self.root / 'target'; dst.mkdir()
        (dst / 'keep').write_text('user work')
        with self.assertRaises(RuntimeError):
            self.mod.link(src, dst)
        self.assertEqual((dst / 'keep').read_text(), 'user work')

    def test_relative_link_install_is_idempotent(self):
        src = self.root / 'source'; src.mkdir()
        dst = self.root / 'target'
        self.mod.link(src, dst)
        self.mod.link(src, dst)
        self.assertEqual(dst.resolve(), src.resolve())
        self.assertFalse(os.path.isabs(os.readlink(dst)))

if __name__ == '__main__':
    unittest.main()
