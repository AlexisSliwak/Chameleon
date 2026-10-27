"""Subpixel image boxes must retain their proportions during rigid fitting."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine.resize import make_units, source_fit, leaf_states, resize
from engine.measure import TextMeasurer
from engine.main import render_to_png
from engine.validation import validate_output
from engine.flow import _choices
from engine.editorial import Unit, _unit


class SubpixelImageTests(unittest.TestCase):
    def test_rigid_fitting_paths_preserve_subpixel_image_proportions(self):
        target = {'width': 120, 'height': 60}
        measurer = TextMeasurer()
        for width, height in [(0.00001, 20), (20, 0.00001), (0.00001, 0.00002)]:
            for rotation in (0, 31):
                with self.subTest(width=width, height=height, rotation=rotation):
                    source = {'canvas': {'width': 100, 'height': 100}, 'elements': [{
                        'id': 'image', 'type': 'image', 'x': 30, 'y': 30,
                        'width': width, 'height': height, 'rotation': rotation,
                        'asset_id': 'solstice_bottle.png', 'fit': 'contain', 'group_id': 'lockup'}]}
                    units = make_units(source, [])
                    outputs = [source_fit(source, target, units, [], measurer)]
                    states = leaf_states(source, units[0], target, measurer, 0.6)
                    self.assertTrue(states)
                    flow_states = _choices(source, units[0], 120, 60, 1, 12, 0.6, 1, measurer)
                    self.assertTrue(flow_states)
                    for state in states:
                        outputs.append({'canvas': target, 'elements': [state.placements[0]]})
                    # Flow states pack visible alpha support; their full boxes
                    # are moved back inside the canvas after packing.
                    for state in flow_states:
                        image = state.placements[0]
                        self.assertAlmostEqual(width/height, image['width']/image['height'],
                                               delta=(width/height)*1e-10)
                    elements = copy.deepcopy(source['elements'])
                    unit = Unit([0], units[0].bounds, [], [], [0])
                    _unit(elements, unit, (0, 0, 120, 60), 12, measurer, target)
                    outputs.append({'canvas': target, 'elements': elements})
                    for output in outputs:
                        image = output['elements'][0]
                        self.assertAlmostEqual(width/height, image['width']/image['height'],
                                               delta=(width/height)*1e-10)
                        self.assertEqual([], validate_output(source, target, output))

    def test_thin_images_resize_and_render_without_mutating_source(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict('os.environ', {'CHAMELEON_ADVISOR': 'off'}):
            for width, height in [(0.00001, 20), (20, 0.00001)]:
                with self.subTest(width=width, height=height):
                    source = {'canvas': {'width': 100, 'height': 100}, 'elements': [{
                        'id': 'image', 'type': 'image', 'x': 30, 'y': 30,
                        'width': width, 'height': height, 'asset_id': 'solstice_bottle.png'}]}
                    original = copy.deepcopy(source)
                    target = {'width': 120, 'height': 60}
                    output = resize(source, target)
                    self.assertEqual(original, source)
                    self.assertEqual([], validate_output(source, target, output))
                    self.assertAlmostEqual(width/height,
                                           output['elements'][0]['width']/output['elements'][0]['height'],
                                           delta=(width/height)*1e-10)
                    self.assertEqual([], render_to_png(output, root/'brand_kit/assets',
                                                       Path(directory)/'output.png', root/'brand_kit/fonts'))
