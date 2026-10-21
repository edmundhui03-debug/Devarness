"""library coverage: everything dev holds maps to a library entry.

Fixture indexes are written by hand, so these run without the YAML parser;
only the real-tree check refreshes, and it runs in the isolated runtime.
"""
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'library.py'
DEV = MODULE.parents[1]
HAS_YAML = importlib.util.find_spec('yaml') is not None


def load():
    spec = importlib.util.spec_from_file_location('dev_library', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(collection, kind, name, path):
    return {'id': f'{collection}:{kind}:{name}', 'name': name, 'kind': kind,
            'collection': collection, 'purpose': 'fixture', 'category': '',
            'path': path, 'owner_ref': 'CLAUDE.md|Fixture', 'owner': 'fixture',
            'scope': '.', 'mode': 'library-only', 'aliases': [], 'exclusions': [],
            'source_present': True, 'configured_clients': [],
            'runtime_status': 'unknown', 'unfinished': False}


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.lib = load()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.write('.claude/skills/markdown-format/SKILL.md', '---\nname: md-format\n---\n')
        self.write('Library/bin/md-format', '#!/usr/bin/env python3\n')
        self.write('.claude/agents/helper.md', '---\nname: helper\n---\n')
        self.write('.mcp.json', json.dumps({'mcpServers': {'laya': {'command': 'x'}}}))
        self.write('.codex/config.toml', 'model = "m"\n\n[mcp_servers.laya]\ncommand = "x"\n'
                                         '[mcp_servers.laya.env]\nA = "1"\n')
        self.write('Library/repos.txt', '# comment\nLibrary/tool\thttps://example.invalid/t\tabc\n')
        self.write('Library/tool/README.md', '# Tool\n')
        self.entries = [entry('dev', 'skill', 'md-format', '.claude/skills/markdown-format/SKILL.md'),
                        entry('dev', 'command', 'md-format', 'Library/bin/md-format'),
                        entry('vendor', 'agent', 'helper', 'Library/tool/agents/helper.md'),
                        entry('dev', 'mcp', 'laya', 'Library/setup/mcp/laya.md'),
                        entry('tool', 'guide', 'README', 'Library/tool/README.md')]

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def link(self, rel, target, is_dir):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, path, target_is_directory=is_dir)
        except OSError as exc:  # Windows without symlink privilege
            self.skipTest(f'symlinks unavailable: {exc}')

    def index_path(self, fingerprints=None):
        index = {'schema': 2, 'fingerprints': fingerprints or {}, 'diagnostics': [],
                 'router': [], 'entries': sorted(self.entries, key=lambda e: e['id'])}
        path = self.root / 'index.json'
        path.write_text(json.dumps(index), encoding='utf-8')
        return path

    def run_cli(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.lib.main(['--root', str(self.root), '--index', str(self.index_path()),
                                  'coverage', *extra])
        return code, out.getvalue() + err.getvalue()

    def test_clean_fixture_passes_with_a_count(self):
        code, output = self.run_cli()
        self.assertEqual(code, 0, output)
        self.assertIn('6 items', output)  # skill, command, agent, 2 MCP registrations, clone

    def test_planted_fake_skill_fails_and_is_named(self):
        self.write('.claude/skills/fake-skill/SKILL.md', '---\nname: fake-skill\n---\n')
        code, output = self.run_cli()
        self.assertEqual(code, 1, output)
        self.assertIn('.claude/skills/fake-skill', output)
        self.assertNotIn('.claude/skills/markdown-format', output)

    def test_every_kind_of_orphan_is_named_in_json(self):
        self.write('Library/bin/orphan', '#!/bin/sh\n')
        self.write('.claude/agents/stray.md', '---\nname: stray\n---\n')
        self.write('.agents/skills/codex-only/SKILL.md', '---\nname: codex-only\n---\n')
        self.write('.codex/config.toml', '[mcp_servers.ghost]\ncommand = "x"\n')
        with open(self.root / 'Library/repos.txt', 'a', encoding='utf-8') as fh:
            fh.write('Library/other\thttps://example.invalid/o\tdef\n')
        code, output = self.run_cli('--json')
        self.assertEqual(code, 1, output)
        result = json.loads(output)
        self.assertEqual(result['status'], 'orphans')
        self.assertEqual(sorted(o['path'] for o in result['orphans']),
                         ['.agents/skills/codex-only', '.claude/agents/stray.md',
                          '.codex/config.toml mcp_servers.ghost', 'Library/bin/orphan',
                          'Library/other'])

    def test_the_mcp_servers_bootstrap_registers_for_the_user_are_held(self):
        # dev registers its servers at user level from bootstrap, not in .mcp.json.
        self.write('Library/bootstrap.sh', 'for server in "laya laya-service 300" "ghost ghost 400"; do\n')
        code, output = self.run_cli('--json')
        self.assertEqual(code, 1, output)
        self.assertEqual([o['path'] for o in json.loads(output)['orphans']],
                         ['Library/bootstrap.sh mcp ghost'])

    def test_a_command_entry_does_not_cover_a_skill_of_the_same_name(self):
        self.entries = [e for e in self.entries if e['kind'] != 'skill']
        code, output = self.run_cli()
        self.assertEqual(code, 1, output)
        self.assertIn('.claude/skills/markdown-format', output)

    def test_links_are_covered_through_their_targets(self):
        self.write('Library/skills/retro/SKILL.md', '---\nname: retro\n---\n')
        self.link('.claude/skills/retro', os.path.join('..', '..', 'Library', 'skills', 'retro'), True)
        # A runtime-built agent link may dangle until its installer runs.
        self.link('.claude/agents/ua-analyzer.md',
                  os.path.join('..', '..', 'Library', '.runtime', 'agents', 'analyzer.md'), False)
        self.entries += [entry('pocock', 'skill', 'retro', 'Library/skills/retro/SKILL.md'),
                         entry('understand', 'agent', 'analyzer', 'Library/tool/agents/analyzer.md')]
        code, output = self.run_cli()
        self.assertEqual(code, 0, output)

    def test_a_link_that_raises_on_is_dir_is_still_held(self):
        # A Windows file link to a directory raises PermissionError on is_dir().
        self.write('Library/skills/retro/SKILL.md', '---\nname: retro\n---\n')
        self.link('.claude/skills/retro', os.path.join('..', '..', 'Library', 'skills', 'retro'), True)
        self.entries.append(entry('pocock', 'skill', 'retro', 'Library/skills/retro/SKILL.md'))
        real_is_dir = Path.is_dir

        def is_dir(path):
            if os.path.islink(path):
                raise PermissionError('denied')
            return real_is_dir(path)

        with patch.object(Path, 'is_dir', is_dir):
            code, output = self.run_cli()
        self.assertEqual(code, 0, output)

    def test_a_mapped_clone_needs_its_mapped_entry(self):
        with open(self.root / 'Library/repos.txt', 'a', encoding='utf-8') as fh:
            fh.write('Library/books\thttps://example.invalid/b\tdef\n')
        with patch.object(self.lib, 'COVERAGE_MAP', {'Library/books': 'dev:command:md-format'}):
            self.assertEqual(self.run_cli()[0], 0)
        with patch.object(self.lib, 'COVERAGE_MAP', {'Library/books': 'dev:command:gone'}):
            code, output = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn('Library/books', output)

    def test_stale_index_is_refused(self):
        stale = {str(self.root / 'Library/bin/md-format'): 'file:0:0:0:bogus:'}
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.lib.main(['--root', str(self.root), '--index',
                                  str(self.index_path(stale)), 'coverage'])
        self.assertEqual(code, 2)
        self.assertIn('stale', err.getvalue())


class RealTreeBridge(unittest.TestCase):
    @unittest.skipIf(HAS_YAML, 'already running in a parser-capable interpreter')
    def test_real_tree_in_isolated_runtime(self):
        python = MODULE.parent / '.runtime/library' / (
            'Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.is_file():
            self.skipTest('isolated parser missing; run Library/setup-library.py --install')
        result = subprocess.run([str(python), str(Path(__file__).resolve()),
                                 'RealTreeTests'], capture_output=True, text=True, timeout=600)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(HAS_YAML, 'covered by the isolated parser-runtime bridge')
class RealTreeTests(unittest.TestCase):
    def test_dev_holds_nothing_without_an_entry(self):
        lib = load()
        with tempfile.TemporaryDirectory() as folder:
            index = str(Path(folder) / 'index.json')
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                lib.main(['--root', str(DEV), '--index', index, 'refresh'])
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(out):
                code = lib.main(['--root', str(DEV), '--index', index, 'coverage'])
        self.assertEqual(code, 0, out.getvalue())


if __name__ == '__main__':
    unittest.main()
