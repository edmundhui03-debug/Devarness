"""Check the shared, instruction-based automatic retrospective wiring."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RetroWiringTests(unittest.TestCase):
    def test_shared_skill_is_auto_discoverable(self):
        claude = ROOT / '.claude/skills/retro-last/SKILL.md'
        agents = ROOT / '.agents/skills/retro-last/SKILL.md'
        self.assertTrue(claude.is_file())
        self.assertTrue(agents.is_file())
        self.assertEqual(claude.resolve(), agents.resolve())
        text = claude.read_text(encoding='utf-8')
        self.assertIn('name: retro-last', text)
        self.assertNotIn('disable-model-invocation: true', text)
        for requirement in ('Before work', 'After work', 'no improvement needed',
                            'Ask the owner', 'extra model calls'):
            self.assertIn(requirement, text)

    def test_router_and_restore_path_require_retro(self):
        # The rule, not its wording: the router is rewritten for dev, and a heading
        # pinned here would fail the rewrite rather than a lost rule.
        router = (ROOT / 'CLAUDE.md').read_text(encoding='utf-8')
        self.assertIn('retro-last', router, 'CLAUDE.md does not name retro-last')
        self.assertIn('every working turn', router.lower(),
                      'Missing automatic-retro rule in CLAUDE.md')
        setup = (ROOT / 'Library/codex-setup.py').read_text(encoding='utf-8')
        self.assertIn('"retro-last"', setup)


if __name__ == '__main__':
    unittest.main()
