"""Library installation refuses foreign commands before running package tools."""
import importlib.util
import io
from contextlib import redirect_stdout
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

LIBRARY = Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('setup_library', LIBRARY / 'setup-library.py')
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bindir = self.root / 'bin'
        self.bindir.mkdir()

    def test_foreign_command_refused_before_package_execution(self):
        command = self.bindir / 'library'
        command.write_text('owner command')
        with patch.object(self.mod.shutil, 'which', return_value='uv'), \
                patch.object(self.mod.runpy, 'run_path',
                             return_value={'link': lambda *args: None}), \
                patch.object(self.mod.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                self.mod.install(self.root, self.bindir)
            run.assert_not_called()
        self.assertEqual(command.read_text(), 'owner command')

    def test_missing_uv_does_not_create_runtime(self):
        with patch.object(self.mod.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError):
                self.mod.install(self.root, self.bindir)
        self.assertFalse((self.root / 'Harness/.runtime').exists())

    def test_install_twice_keeps_owned_links(self):
        source = self.root / 'Harness/bin/library'
        source.parent.mkdir(parents=True)
        source.write_text('# launcher')
        skill = self.root / '.claude/skills/library'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('# skill')
        python = self.mod.python_path(self.root)
        python.parent.mkdir(parents=True)
        python.write_text('fixture executable; subprocess is mocked')

        def link(src, target):
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_symlink():
                target.symlink_to(src, target_is_directory=True)

        with patch.object(self.mod.shutil, 'which', return_value='uv'), \
                patch.object(self.mod.runpy, 'run_path', return_value={'link': link}), \
                patch.object(self.mod.subprocess, 'run',
                             return_value=subprocess.CompletedProcess([], 0)) as run:
            self.mod.install(self.root, self.bindir)
            self.mod.install(self.root, self.bindir)
        self.assertEqual((self.bindir / 'library').resolve(), source.resolve())
        self.assertEqual((self.root / '.agents/skills/library').resolve(), skill.resolve())
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all('--require-hashes' in c.args[0] for c in run.call_args_list))

    def test_parser_failure_is_not_ready(self):
        python = self.mod.python_path(self.root)
        python.parent.mkdir(parents=True)
        python.write_text('fixture executable; subprocess is mocked')
        with patch.object(self.mod.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 1)) as run:
            issues = self.mod.check(self.root)
        self.assertIn('isolated parser check failed', issues)
        self.assertIn('import yaml', run.call_args.args[0][-1])

    def test_main_missing_setup_exits_nonzero(self):
        with patch.object(self.mod, 'ROOT', self.root), redirect_stdout(io.StringIO()):
            self.assertEqual(self.mod.main(['--check']), 1)

    def test_check_missing_files_is_not_ready(self):
        self.assertTrue(self.mod.check(self.root))


if __name__ == '__main__':
    unittest.main()
