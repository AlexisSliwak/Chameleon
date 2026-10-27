"""Exercise numeric JSON representations through the real offline pipeline."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from engine.main import run_batch
from engine.validation import validate_output


class NumericInputTests(unittest.TestCase):
    def test_integral_float_identity_and_retarget_publish_real_output_pairs(self):
        source = {'canvas': {'width': 128.0, 'height': 128.0}, 'elements': [{
            'id': 'title', 'type': 'text', 'x': 10, 'y': 10, 'width': 100, 'height': 40,
            'content': 'Hello world', 'font_family': 'Solstice Sans', 'font_size': 12,
            'color': '#000', 'z_index': 1.0, 'max_lines': 2.0,
            'style_runs': [{'start': 0.0, 'end': 4.0, 'font_weight': 'bold'}]}]}
        original = copy.deepcopy(source)
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict('os.environ', {'CHAMELEON_ADVISOR': 'off'}):
            inputs, outputs = Path(directory)/'input', Path(directory)/'output'
            inputs.mkdir()
            for name, target in [('identity', source['canvas']),
                                 ('retarget', {'width': 100.0, 'height': 80.0})]:
                (inputs/f'{name}.json').write_text(json.dumps({'source': source, 'target_canvas': target}))
            before = {p.name: p.read_bytes() for p in inputs.iterdir()}
            self.assertEqual(0, run_batch(inputs, outputs, root/'brand_kit/assets', root/'brand_kit/fonts'))
            self.assertEqual(before, {p.name: p.read_bytes() for p in inputs.iterdir()})
            self.assertEqual(original, source)
            self.assertEqual(4, len(list(outputs.iterdir())))
            for name, size in [('identity', (128, 128)), ('retarget', (100, 80))]:
                output = json.loads((outputs/f'{name}_output.json').read_text())
                self.assertEqual([], validate_output(source, dict(zip(('width', 'height'), size)), output))
                self.assertEqual(source['elements'][0]['style_runs'], output['elements'][0]['style_runs'])
                with Image.open(outputs/f'{name}_output.png') as image:
                    self.assertEqual('PNG', image.format)
                    self.assertEqual(size, image.size)
                    image.verify()
