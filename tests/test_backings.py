import copy
import unittest
from pathlib import Path
import json

from engine.resize import make_units, resize_with_diagnostics, assess
from engine.measure import TextMeasurer


def supported_copy():
    return {'canvas':{'width':400,'height':300},'elements':[
        dict(id='panel',type='shape',shape_type='rectangle',x=20,y=20,width=360,height=100,
             fill_color='rgba(0,0,0,1)',z_index=0),
        dict(id='title',type='text',x=40,y=40,width=320,height=60,content='A clear headline',
             font_family='Solstice Sans',font_size=24,color='rgba(255,255,255,1)',z_index=1)]}


class BackingTests(unittest.TestCase):
    def test_readable_identity_with_backing_is_unchanged(self):
        source = supported_copy()
        saved = copy.deepcopy(source)
        output,diagnostics = resize_with_diagnostics(source,source['canvas'])
        self.assertEqual(saved,source)
        self.assertEqual(saved,output)
        self.assertEqual('identity',diagnostics['method'])

    def test_inference_does_not_add_groups_or_absorb_explicit_group(self):
        source = supported_copy()
        saved = copy.deepcopy(source)
        self.assertEqual([[0,1]],[u.indices for u in make_units(source,[])])
        self.assertEqual(saved,source)
        source['elements'][1]['group_id'] = ''
        self.assertEqual(2,len(make_units(source,[])))

    def test_foreground_rectangle_is_not_inferred_as_backing(self):
        source = supported_copy()
        source['elements'][0]['z_index'] = 2
        self.assertEqual(2,len(make_units(source,[])))
        self.assertGreater(assess(source,source,[],TextMeasurer())['collision_proxy'],0)

    def test_later_tied_rectangle_is_not_safe_backing(self):
        source = supported_copy()
        source['elements'][0]['z_index'] = 1
        source['elements'].reverse()
        self.assertEqual(2,len(make_units(source,[])))
        self.assertGreater(assess(source,source,[],TextMeasurer())['collision_proxy'],0)

    def test_partial_overlap_does_not_imply_attachment(self):
        source = supported_copy()
        source['elements'][1]['x'] = 370
        self.assertEqual(2,len(make_units(source,[])))

    def test_near_aspect_sparse_design_retains_vertical_brand_anchor(self):
        task = json.loads((Path(__file__).resolve().parents[1]/'input/chameleon_sample_level1_warmup.json').read_text())
        design,_ = resize_with_diagnostics(task['source'],dict(width=1080,height=1350))
        images = [e for e in design['elements'] if e['type']=='image' and e.get('fit')!='cover']
        heading = max((e for e in design['elements'] if e['type']=='text'),key=lambda e:e['font_size'])
        # The source brand mark sits above its message. A modest aspect change
        # must not flatten all three into one disconnected middle row.
        self.assertLess(images[0]['y']+images[0]['height']/2, heading['y'])
