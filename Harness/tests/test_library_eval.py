"""Scorer must fail broken data instead of grading errors as successes."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

LIBRARY = Path(__file__).resolve().parents[1]


class EvalTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('library_eval', LIBRARY / 'library-eval.py')
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.cases = [{'query': 'test', 'expected': 'dev:skill:test', 'project': '.'}] * 20

    def test_empty_results_fail_all_twenty(self):
        with patch.object(self.mod, 'search', return_value=[]):
            result = self.mod.evaluate({}, self.cases)
        self.assertEqual(result['passed'], 0)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['total'], 20)

    def test_search_exception_is_an_error(self):
        with patch.object(self.mod, 'search', side_effect=ValueError('bad index')):
            result = self.mod.evaluate({}, self.cases)
        self.assertEqual(len(result['errors']), 20)
        self.assertFalse(result['accepted'])

    def test_good_results_meet_the_frozen_threshold(self):
        with patch.object(self.mod, 'search', return_value=[{'entry': {'id': 'dev:skill:test'}}]):
            result = self.mod.evaluate({}, self.cases)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['passed'], 20)

    def test_incomplete_index_cannot_pass_even_with_good_ranking(self):
        with patch.object(self.mod, 'search', return_value=[{'entry': {'id': 'dev:skill:test'}}]):
            result = self.mod.evaluate({'diagnostics': ['missing source']}, self.cases)
        self.assertFalse(result['accepted'])
        self.assertTrue(result['errors'])

    def test_wrong_case_count_never_passes(self):
        with patch.object(self.mod, 'search', return_value=[{'entry': {'id': 'dev:skill:test'}}]):
            self.assertFalse(self.mod.evaluate({}, self.cases[:1])['accepted'])


if __name__ == '__main__':
    unittest.main()
