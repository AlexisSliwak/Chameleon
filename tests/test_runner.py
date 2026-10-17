import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import main as runner


def task():
    return {'source': {'canvas': {'width': 100, 'height': 100}, 'elements': [
        {'id': 'box', 'type': 'shape', 'x': 0, 'y': 0, 'width': 20, 'height': 20,
         'shape_type': 'rectangle', 'fill_color': '#000'}]},
        'target_canvas': {'width': 100, 'height': 100}}


def fake_render(design, assets, destination, fonts=None):
    # Boundary fake: tests publication, not the actual official rendering backend.
    Path(destination).write_bytes(b'PNG-test-artifact')
    return ['expected missing fixture asset']


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs, self.outputs = self.root / 'input', self.root / 'output'
        self.inputs.mkdir()
        self.outputs.mkdir()

    def write_task(self, name='sample', value=None):
        (self.inputs / f'{name}.json').write_text(json.dumps(task() if value is None else value))

    def run_batch(self, resize=None, render=fake_render):
        log = io.StringIO()
        operation = resize or (lambda s, t: copy.deepcopy(s))
        with patch.object(runner, 'resize_with_diagnostics',
                          lambda s, t, **kw: (operation(s, t), {'method': 'test'})), \
                patch.object(runner, 'render_to_png', render), contextlib.redirect_stderr(log):
            status = runner.run_batch(self.inputs, self.outputs, self.root / 'assets')
        return status, [json.loads(line) for line in log.getvalue().splitlines()]

    def test_pair_success_and_separate_diagnostics(self):
        self.write_task()
        status, records = self.run_batch()
        self.assertEqual(0, status)
        self.assertEqual('ok', records[0]['status'])
        self.assertEqual(['expected missing fixture asset'], records[0]['warnings'])
        self.assertIn('render', records[0]['timings_seconds'])
        self.assertEqual(task()['source'], json.loads((self.outputs / 'sample_output.json').read_text()))
        self.assertTrue((self.outputs / 'sample_output.png').is_file())
        self.assertEqual(2, len(list(self.outputs.iterdir())))

    def test_renderer_failure_removes_stale_pair_and_continues(self):
        self.write_task('a')
        self.write_task('b')
        for suffix in ('json', 'png'):
            (self.outputs / f'a_output.{suffix}').write_text('stale')
        calls = []
        def render(*args):
            calls.append(1)
            if len(calls) == 1:
                raise ImportError('renderer missing')
            return fake_render(*args)
        status, records = self.run_batch(render=render)
        self.assertEqual(1, status)
        self.assertEqual(['failed', 'ok'], [r['status'] for r in records])
        self.assertFalse((self.outputs / 'a_output.json').exists())
        self.assertFalse((self.outputs / 'a_output.png').exists())
        self.assertTrue((self.outputs / 'b_output.png').exists())

    def test_bad_input_and_mutation_fail(self):
        self.write_task(value={'bad': True})
        self.assertEqual(1, self.run_batch()[0])
        self.write_task()
        def mutate(s, t):
            s['elements'][0]['width'] = 10
            return s
        status, records = self.run_batch(resize=mutate)
        self.assertEqual(1, status)
        self.assertIn('mutated', records[0]['error'])
        self.assertEqual([], list(self.outputs.iterdir()))

    def test_partial_publish_rolls_back(self):
        self.write_task()
        real_replace = runner.os.replace
        calls = []
        def fail_second(src, dst):
            calls.append(1)
            if len(calls) == 2:
                raise OSError('simulated publish failure')
            return real_replace(src, dst)
        with patch.object(runner.os, 'replace', side_effect=fail_second):
            status, records = self.run_batch()
        self.assertEqual(1, status)
        self.assertEqual([], list(self.outputs.iterdir()))

    def test_missing_png_and_empty_batch_fail(self):
        self.assertEqual(1, self.run_batch()[0])
        self.write_task()
        self.assertEqual(1, self.run_batch(render=lambda *a: [])[0])
        self.assertEqual([], list(self.outputs.iterdir()))

    def test_font_asset_configuration_reaches_both_consumers(self):
        self.write_task()
        captured = {}
        def operation(s, t, **kwargs):
            captured.update(kwargs)
            return copy.deepcopy(s), {'method': 'configured'}
        def render(design, assets, destination, fonts):
            self.assertEqual(captured['assets_dir'], assets)
            self.assertEqual(captured['fonts_dir'], fonts)
            return fake_render(design, assets, destination, fonts)
        with patch.object(runner, 'resize_with_diagnostics', operation), \
                patch.object(runner, 'render_to_png', render), \
                contextlib.redirect_stderr(io.StringIO()):
            status = runner.run_batch(self.inputs, self.outputs, self.root / 'custom' / 'assets')
        self.assertEqual(0, status)
        self.assertEqual(self.root / 'custom' / 'fonts', captured['fonts_dir'])

    def test_invalid_output_rejected_before_rendering(self):
        self.write_task()
        def invalid(s, t):
            o = copy.deepcopy(s)
            o['elements'].append(copy.deepcopy(o['elements'][0]))
            return o
        def should_not_render(*args):
            self.fail('invalid output reached renderer')
        status, records = self.run_batch(resize=invalid, render=should_not_render)
        self.assertEqual(1, status)
        self.assertIn('exactly once', records[0]['error'])
        self.assertEqual([], list(self.outputs.iterdir()))

    def test_same_input_output_rejected_without_deleting_tasks(self):
        self.write_task('sample')
        self.write_task('sample_output')
        before = {p.name: p.read_bytes() for p in self.inputs.iterdir()}
        with contextlib.redirect_stderr(io.StringIO()):
            status = runner.run_batch(self.inputs, self.inputs, self.root / 'assets')
        self.assertEqual(1, status)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.inputs.iterdir()})


if __name__ == '__main__':
    unittest.main()
