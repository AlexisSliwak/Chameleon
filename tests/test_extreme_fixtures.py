from pathlib import Path
import unittest
from scripts.review_hard_cases import load_suite
from engine.validation import validate_source,validate_target


class ExtremeFixtureTests(unittest.TestCase):
    def test_adversarial_suite_is_valid_and_retains_declared_pressure(self):
        root=Path(__file__).resolve().parents[1]
        suite,families=load_suite(root/'tests/fixtures/extreme-challenges')
        self.assertEqual(len(families),5)
        self.assertEqual(sum(len(f['targets']) for f,t in families),16)
        self.assertGreaterEqual(max(len(t['source']['elements']) for f,t in families),63)
        for family,task in families:
            self.assertEqual(validate_source(task['source']),[])
            for target in family['targets']:self.assertEqual(validate_target(target['canvas']),[])
            for e in task['source']['elements']:
                if e['type']=='image':self.assertTrue((root/'brand_kit/assets'/e['asset_id']).is_file())
        texts=[e for f,t in families for e in t['source']['elements'] if e['type']=='text']
        self.assertTrue(any(len(e['content'])>300 for e in texts))
        self.assertTrue(any(e.get('opacity',1)<.05 for e in texts))
        self.assertTrue(any(e.get('rotation') for e in texts))
