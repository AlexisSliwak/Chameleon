import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import evaluate, evaluate_challenges


def fake_module(name, **members):
    module = types.ModuleType(name)
    module.__dict__.update(members)
    return module


class EvaluationExitTests(unittest.TestCase):
    def run_case(self, script, failure):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs, assets, fonts = (root/name for name in ('input', 'assets', 'fonts'))
            for directory in (inputs, assets, fonts):
                directory.mkdir()
            source = {'canvas': {'width': 10, 'height': 10}, 'elements': []}
            target = {'width': 20, 'height': 10}
            task = {'source': source, 'target_canvas': target}
            for level in range(1, 4):
                (inputs/f'chameleon_sample_level{level}.json').write_text(json.dumps(task))
            (inputs/'challenge-matrix.json').write_text(json.dumps({'families': [
                {'file': 'chameleon_sample_level1.json', 'targets': [target]}]}))

            def render(design, assets, path, fonts):
                if failure == 'source' and path.name == 'source.png':
                    raise RuntimeError('source preview failed')
                if failure == 'output' and path.name == 'output.png':
                    raise RuntimeError('output render failed')
                # Boundary fake for exit/report behavior; real PNGs have separate tests.
                path.write_bytes(b'rendered artifact')
                return []

            fakes = {
                'engine.resize': fake_module('engine.resize', background_indices=lambda s: [],
                    assess=lambda *a: {}, resize_with_diagnostics=lambda s, t, **kw:
                    ({'canvas': t, 'elements': []}, {})),
                'engine.measure': fake_module('engine.measure', TextMeasurer=lambda *a: None),
                'engine.validation': fake_module('engine.validation', validate_output=lambda *a:
                    ['changed element'] if failure == 'contract' else []),
                'engine.main': fake_module('engine.main', render_to_png=render),
            }
            output = root/'results'
            with patch.dict(sys.modules, fakes), patch.object(script, 'gallery'), \
                    contextlib.redirect_stdout(io.StringIO()):
                status = script.main(['--output-dir', str(output), '--input-dir', str(inputs),
                    '--assets-dir', str(assets), '--fonts-dir', str(fonts)])
            result = json.loads((output/'results.json').read_text())
            summary = json.loads((output/'summary.json').read_text())
            self.assertTrue(result['cases'])
            if failure == 'contract':
                self.assertTrue(all(r['status'] == 'rendered-invalid' for r in result['cases']))
                self.assertTrue(all((output/r['png']).is_file() for r in result['cases']))
                self.assertTrue(all(r['validation_errors'] for r in result['cases']))
                self.assertEqual(len(result['cases']), summary['methods']['full']['invalid_contract'])
            elif failure == 'source':
                self.assertTrue(all(r['status'] == 'rendered-valid' for r in result['cases']))
                self.assertGreater(summary['source_render_failures'], 0)
            return status

    def test_invalid_rendered_outputs_fail_and_remain_in_reports(self):
        for script in (evaluate, evaluate_challenges):
            with self.subTest(script=script.__name__):
                self.assertEqual(1, self.run_case(script, 'contract'))

    def test_missing_source_previews_fail_even_when_outputs_render(self):
        for script in (evaluate, evaluate_challenges):
            with self.subTest(script=script.__name__):
                self.assertEqual(1, self.run_case(script, 'source'))

    def test_output_errors_fail_and_complete_runs_succeed(self):
        for script in (evaluate, evaluate_challenges):
            with self.subTest(script=script.__name__):
                self.assertEqual(1, self.run_case(script, 'output'))
                self.assertEqual(0, self.run_case(script, None))
