"""Behavioral checks for bounded readability recovery, not preference certification."""
import json
import os
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from engine.resize import resize_with_diagnostics
from engine.validation import validate_output

ROOT=Path(__file__).resolve().parents[1]

class ExpandedSearchTests(unittest.TestCase):
    def test_rotated_banner_recovers_body_and_action_without_font_regression(self):
        task=json.loads((ROOT/'tests/fixtures/design-families/rotated-workshop.json').read_text())
        source=task['source'];before=deepcopy(source);target=dict(width=728,height=90)
        def disabled(source,best,*args):return best,dict(status='test_disabled',candidates=0,valid_candidates=0)
        with patch.dict(os.environ,{'CHAMELEON_ADVISOR':'off'}):
            with patch('engine.resize.expand_tiny_text_search',side_effect=disabled):baseline,_=resize_with_diagnostics(source,target)
            result,info=resize_with_diagnostics(source,target)
        self.assertEqual('selected',info['expanded_search']['status'])
        fonts={e['id']:e['font_size'] for e in result['elements'] if e['type']=='text'}
        original={e['id']:e['font_size'] for e in baseline['elements'] if e['type']=='text'}
        self.assertTrue(all(fonts[k]>=v for k,v in original.items()))
        self.assertGreaterEqual(fonts['description'],12)
        self.assertGreaterEqual(fonts['action-label'],8)
        self.assertEqual(0,info['hierarchy_inversion'])
        self.assertEqual([],validate_output(source,target,result));self.assertEqual(before,source)
        self.assertEqual(0,info['text_overflow_px']);self.assertEqual(0,info['collision_proxy'])

    def test_readable_result_does_not_trigger_expansion(self):
        task=json.loads((ROOT/'input/chameleon_sample_level1_warmup.json').read_text())
        with patch.dict(os.environ,{'CHAMELEON_ADVISOR':'off'}):
            _,info=resize_with_diagnostics(task['source'],task['target_canvas'])
        self.assertEqual('not_needed',info['expanded_search']['status'])
        self.assertEqual(0,info['expanded_search']['candidates'])
