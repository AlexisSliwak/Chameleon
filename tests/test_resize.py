"""Public resize contract tests; run unittest discovery from implementation/ with renderer deps."""
import copy
from collections import Counter
import json
import math
from pathlib import Path
import unittest

from engine.resize import resize

ROOT = Path(__file__).resolve().parents[1]
EDITABLE = {'x', 'y', 'width', 'height', 'font_size'}
TARGETS = [(1080,1080), (1080,1920), (1920,1080), (1600,400), (728,90), (320,320), (90,728)]


def text_source(**updates):
    element = dict(id='text-one', type='text', x=40., y=40., width=240., height=80.,
                   content='Keep every word', font_family='Solstice Sans', font_size=24.,
                   color='rgba(0,0,0,1)', z_index=1)
    element.update(updates)
    return dict(canvas=dict(width=400, height=240), elements=[element])


class ResizeTests(unittest.TestCase):
    def assert_contract(self, source, target, output):
        self.assertEqual(target, output['canvas'])
        self.assertEqual(Counter(e['id'] for e in source['elements']),
                         Counter(e['id'] for e in output['elements']))
        original = {e['id']: e for e in source['elements']}
        for item in output['elements']:
            before = original[item['id']]
            self.assertEqual({k:v for k,v in before.items() if k not in EDITABLE},
                             {k:v for k,v in item.items() if k not in EDITABLE})
            for field in ('x','y','width','height'):
                self.assertTrue(math.isfinite(item[field]))
            self.assertGreaterEqual(item['width'], 0)
            self.assertGreaterEqual(item['height'], 0)
            # Independent corner rotation, rather than engine bound validator.
            cx, cy = item['x']+item['width']/2, item['y']+item['height']/2
            angle = math.radians(item.get('rotation', 0))
            for x in (-item['width']/2, item['width']/2):
                for y in (-item['height']/2, item['height']/2):
                    px = cx+x*math.cos(angle)-y*math.sin(angle)
                    py = cy+x*math.sin(angle)+y*math.cos(angle)
                    self.assertGreaterEqual(px, -.001)
                    self.assertGreaterEqual(py, -.001)
                    self.assertLessEqual(px, target['width']+.001)
                    self.assertLessEqual(py, target['height']+.001)
            if item['type'] == 'text':
                self.assertGreaterEqual(item['font_size'], 1)
            if item['type'] == 'image' and item.get('fit', 'contain') != 'cover':
                self.assertAlmostEqual(before['width']*item['height'],
                                       before['height']*item['width'], delta=.001)

    def test_already_readable_identity_is_unchanged(self):
        source = text_source()
        self.assertEqual(source, resize(source, source['canvas']))

    def test_deterministic_and_does_not_mutate_input(self):
        source, target = text_source(), dict(width=600, height=160)
        before, target_before = copy.deepcopy(source), dict(target)
        first = resize(source, target)
        self.assertEqual(first, resize(source, target))
        self.assertEqual(before, source)
        self.assertEqual(target_before, target)
        self.assert_contract(source, target, first)

    def test_samples_all_declared_targets(self):
        for path in sorted((ROOT/'input').glob('*.json')):
            task = json.loads(path.read_text())
            targets = set(TARGETS) | {(task['target_canvas']['width'], task['target_canvas']['height'])}
            for w,h in sorted(targets):
                with self.subTest(source=path.name, target=(w,h)):
                    source = copy.deepcopy(task['source'])
                    output = resize(source, dict(width=w, height=h))
                    self.assert_contract(task['source'], dict(width=w, height=h), output)
                    self.assertEqual(task['source'], source)

    def test_bijective_id_rename_does_not_change_geometry(self):
        task = json.loads((ROOT/'input/chameleon_sample_level1_warmup.json').read_text())
        source = task['source']
        renamed = copy.deepcopy(source)
        reverse = {}
        for i, item in enumerate(renamed['elements']):
            replacement = 'opaque-' + str(17-i)
            reverse[replacement] = item['id']
            item['id'] = replacement
        target = dict(width=1600,height=400)
        expected = resize(source,target)
        actual = resize(renamed,target)
        for item in actual['elements']:
            item['id'] = reverse[item['id']]
        self.assertEqual(expected, actual)

    def test_rotated_text_fits_by_its_corners(self):
        source = text_source(rotation=35., content='Rotated text')
        target = dict(width=210,height=130)
        self.assert_contract(source,target,resize(source,target))

    def test_long_token_and_styles_are_preserved(self):
        source = text_source(content='ABCDEFGHIJKLMNO rest', capitalize=True,
                             letter_spacing=1.3, font_style='italic', line_height=1.15,
                             style_runs=[dict(start=2,end=8,font_weight='bold',color='rgba(0,0,0,1)')])
        target = dict(width=180,height=100)
        self.assert_contract(source,target,resize(source,target))


if __name__ == '__main__':
    unittest.main()
