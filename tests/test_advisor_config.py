import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from engine.resize import resize


class AdvisorConfigTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.source = json.loads((root/'input/chameleon_sample_level1_warmup.json').read_text())['source']

    def test_invalid_modes_are_rejected_for_identity_and_retargeting(self):
        for mode in ('', 'invalid', 'critic'):
            for target in (self.source['canvas'], {'width': 400, 'height': 500}):
                with self.subTest(mode=mode, target=target), \
                        patch.dict('os.environ', {'CHAMELEON_ADVISOR': mode}), \
                        patch('engine.semantics.get_model') as get_model:
                    with self.assertRaisesRegex(ValueError, 'off or regions'):
                        resize(self.source, target)
                    get_model.assert_not_called()

    def test_valid_identity_modes_preserve_source_without_loading_model(self):
        original = copy.deepcopy(self.source)
        for mode in ('off', 'regions'):
            with self.subTest(mode=mode), \
                    patch.dict('os.environ', {'CHAMELEON_ADVISOR': mode}), \
                    patch('engine.semantics.get_model') as get_model:
                self.assertEqual(original, resize(self.source, self.source['canvas']))
                self.assertEqual(original, self.source)
                get_model.assert_not_called()
