import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from PIL import Image, ImageDraw
from engine.composition import composition_metrics, visible_image, optical_bounds, _alpha_support, repeated_group_flow


class FixtureMeasurer:
    """Known glyph rectangles isolate ranking from the real typography adapter."""
    def measure(self, e):
        size = e['font_size']
        return SimpleNamespace(left=0., top=0., right=min(e['width'], size*4),
                               bottom=size*.8, lines=1, missing_glyphs=0)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.assets = Path(self.temp.name)
        image = Image.new('RGBA', (100, 100))
        ImageDraw.Draw(image).rectangle((25, 0, 74, 99), fill='orange')
        image.save(self.assets/'product.png')
        self.source = {'canvas': {'width': 400, 'height': 400}, 'elements': [
            {'id': 'a', 'type': 'image', 'asset_id': 'product.png', 'x': 0, 'y': 50, 'width': 200, 'height': 200},
            {'id': 'b', 'type': 'text', 'content': 'Heading', 'font_size': 48, 'x': 210, 'y': 20, 'width': 180, 'height': 60},
            {'id': 'c', 'type': 'text', 'content': 'Action', 'font_size': 20, 'x': 210, 'y': 100, 'width': 160, 'height': 40},
            {'id': 'd', 'type': 'text', 'content': 'Detail', 'font_size': 14, 'x': 210, 'y': 160, 'width': 160, 'height': 30}]}
        self.measurer = FixtureMeasurer()

    def score(self, output):
        return composition_metrics(self.source, output, self.measurer, self.assets)

    def test_tiny_hero_giant_action_loses_despite_larger_average_font(self):
        good = copy.deepcopy(self.source)
        bad = copy.deepcopy(self.source)
        bad['elements'][0].update(width=40, height=40)
        bad['elements'][2]['font_size'] = 64
        self.assertGreater(sum(e['font_size'] for e in bad['elements'] if e['type']=='text'),
                           sum(e['font_size'] for e in good['elements'] if e['type']=='text'))
        self.assertGreater(self.score(good)['score'], self.score(bad)['score'] + 2)
        self.assertLess(self.score(bad)['hero_retention'], .3)
        self.assertGreater(self.score(bad)['hierarchy_loss'], 0)

    def test_large_action_cannot_offset_unreadable_detail(self):
        bad = copy.deepcopy(self.source)
        bad['elements'][2]['font_size'] = 80
        bad['elements'][3]['font_size'] = 2
        self.assertGreater(self.score(self.source)['score'], self.score(bad)['score'])
        self.assertGreater(self.score(bad)['copy_floor_loss'], 1)

    def test_alpha_padding_and_contain_are_measured(self):
        e = dict(self.source['elements'][0], width=200, height=100)
        bounds, area = visible_image(e, self.assets)
        self.assertAlmostEqual(area, 5000, delta=300)
        self.assertAlmostEqual(bounds[2]-bounds[0], 50, delta=4)
        self.assertAlmostEqual(bounds[3]-bounds[1], 100, delta=2)

    def test_missing_asset_not_mistaken_for_hero(self):
        self.source['elements'][0]['asset_id'] = 'missing.png'
        self.assertEqual(0, self.score(self.source)['foreground_image_count'])

    def test_full_canvas_contain_product_is_not_discarded_as_background(self):
        self.source['elements'][0].update(x=0, y=0, width=400, height=400, fit='contain')
        self.assertEqual(1, self.score(self.source)['foreground_image_count'])

    def test_scaled_images_reuse_bounded_mask_without_changing_support(self):
        _alpha_support.cache_clear()
        first = optical_bounds(self.source['elements'][0], self.assets)
        second = optical_bounds(dict(self.source['elements'][0], width=400, height=400), self.assets)
        self.assertAlmostEqual(second[2]-second[0], 2*(first[2]-first[0]))
        self.assertEqual(1, _alpha_support.cache_info().misses)

    def test_real_assessment_distinguishes_padding_from_opaque_image(self):
        from engine.resize import assess
        source = copy.deepcopy(self.source)
        source['elements'] = [source['elements'][0], source['elements'][3]]
        padding = copy.deepcopy(source)
        padding['elements'][1].update(x=0, y=100, width=30, height=30)
        opaque = copy.deepcopy(padding)
        opaque['elements'][1]['x'] = 80
        padding_metrics = assess(source, padding, [], self.measurer, assets_dir=self.assets)
        opaque_metrics = assess(source, opaque, [], self.measurer, assets_dir=self.assets)
        self.assertEqual(0, padding_metrics['collision_proxy'])
        self.assertGreater(opaque_metrics['collision_proxy'], 0)

    def test_names_and_strings_do_not_supply_roles(self):
        before = self.score(self.source)
        for e in self.source['elements']:
            e['id'] = 'anonymous-' + e['id']
            if e['type'] == 'text':
                e['content'] = 'Unrelated'
        self.assertEqual(before, self.score(self.source))

    def test_group_separation_penalized_without_mutating_styles(self):
        self.source['elements'][2]['group_id'] = ''
        self.source['elements'].append({'id':'e', 'type':'shape', 'group_id':'',
                                      'x':200, 'y':95, 'width':180, 'height':50})
        bad = copy.deepcopy(self.source)
        bad['elements'][-1]['y'] = 340
        saved = copy.deepcopy(bad)
        self.assertGreater(self.score(bad)['cohesion_loss'], self.score(self.source)['cohesion_loss'])
        self.assertEqual(saved, bad)

    def test_selector_preserves_dark_support_for_white_headline(self):
        from engine.resize import resize_with_diagnostics
        source = {'canvas': {'width':400, 'height':400}, 'elements': [
            {'id':'a', 'type':'shape', 'shape_type':'rectangle', 'fill_color':'rgba(255,255,255,1)',
             'x':0, 'y':0, 'width':400, 'height':400},
            {'id':'b', 'type':'shape', 'shape_type':'rectangle', 'fill_color':'rgba(0,0,0,1)',
             'x':20, 'y':20, 'width':360, 'height':100},
            {'id':'c', 'type':'text', 'content':'A clear headline', 'font_family':'Solstice Sans',
             'font_size':32, 'color':'rgba(255,255,255,1)', 'x':40, 'y':40, 'width':320, 'height':60},
            {'id':'d', 'type':'text', 'content':'Supporting information', 'font_family':'Solstice Sans',
             'font_size':18, 'color':'rgba(0,0,0,1)', 'x':40, 'y':160, 'width':320, 'height':70}]}
        original = copy.deepcopy(source)
        design, diagnostics = resize_with_diagnostics(source, {'width':600, 'height':900})
        self.assertEqual(original, source)
        self.assertLess(diagnostics['raster']['low_contrast_proxy'], .05)
        by_id = {e['id']:e for e in design['elements']}
        panel, heading = by_id['b'], by_id['c']
        self.assertGreaterEqual(heading['x'], panel['x'])
        self.assertGreaterEqual(heading['y'], panel['y'])
        self.assertLessEqual(heading['x']+heading['width'], panel['x']+panel['width']+.01)
        self.assertLessEqual(heading['y']+heading['height'], panel['y']+panel['height']+.01)


class RepeatedFlowTests(unittest.TestCase):
    def setUp(self):
        self.source = {'canvas': {'width':400, 'height':240}, 'elements': []}
        for i in range(3):
            self.source['elements'].extend([
                {'id':f'panel-{i}', 'group_id':str(i), 'type':'shape',
                 'x':120*i, 'y':20, 'width':100, 'height':100},
                {'id':f'label-{i}', 'group_id':str(i), 'type':'text', 'content':'Item',
                 'font_size':16, 'x':120*i+10, 'y':40, 'width':80, 'height':30}])
        self.source['elements'].append({'id':'outside', 'type':'text', 'content':'Action',
                                       'font_size':16, 'x':20, 'y':180, 'width':80, 'height':10})

    def column(self, reverse=False):
        design = copy.deepcopy(self.source)
        design['canvas'] = {'width':150, 'height':450}
        for e in design['elements']:
            if e.get('group_id') is not None:
                i = int(e['group_id'])
                e['x'] += 20-120*i
                e['y'] += 130*((2-i) if reverse else i)-20
            else:
                e['y'] = 400
        return design

    def test_ordered_column_preserves_row_sequence_reversal_does_not(self):
        good = repeated_group_flow(self.source, self.column())
        bad = repeated_group_flow(self.source, self.column(reverse=True))
        self.assertEqual(1, good['repeated_series_count'])
        self.assertEqual(0, good['peer_order_loss'])
        self.assertEqual(1, bad['peer_order_loss'])
        self.assertEqual(0, good['peer_scale_loss'])

    def test_unrelated_action_between_cards_is_penalized(self):
        good = self.column()
        bad = copy.deepcopy(good)
        bad['elements'][-1]['y'] = 113
        self.assertEqual(0, repeated_group_flow(self.source, good)['series_intrusion_loss'])
        self.assertGreater(repeated_group_flow(self.source, bad)['series_intrusion_loss'], 0)

    def test_unequal_peer_scaling_and_ambiguous_source(self):
        bad = self.column()
        for e in bad['elements']:
            if e.get('group_id') == '0':
                e['width'] *= .3
                e['height'] *= .3
        self.assertGreater(repeated_group_flow(self.source, bad)['peer_scale_loss'], .5)
        for e in self.source['elements']:
            if e.get('group_id') == '2':
                e['y'] += 160
        self.assertEqual(0, repeated_group_flow(self.source, self.source)['repeated_series_count'])


if __name__ == '__main__':
    unittest.main()
