import copy
import itertools
import unittest

from engine.flow import pack_lines, flow_candidates
from engine.frontier import State
from engine.measure import TextMeasurer
from engine.resize import background_indices, make_units, assess
from engine.validation import validate_output


def leaf(i,w,h):
    return State(w,h,0,{i:dict(x=0.,y=0.,width=w,height=h)})


class OrderedPackingTests(unittest.TestCase):
    def test_small_frontier_matches_independent_exhaustive_feasibility(self):
        dimensions = [[(30,10),(15,25)],[(40,10),(20,30)],[(25,12),(12,24)]]
        options = [[leaf(i,w,h) for w,h in pairs] for i,pairs in enumerate(dimensions)]
        original = copy.deepcopy(options)
        # Enumerate leaf choices and all contiguous partitions independently.
        for width in (35,55,100):
            minimum = float('inf')
            for choice in itertools.product(*dimensions):
                for cuts in itertools.product((False,True),repeat=2):
                    rows=[[]]
                    for i,box in enumerate(choice):
                        if i and cuts[i-1]:rows.append([])
                        rows[-1].append(box)
                    if all(sum(w for w,h in row)+2*(len(row)-1)<=width for row in rows):
                        minimum=min(minimum,sum(max(h for w,h in row) for row in rows)+2*(len(rows)-1))
            for height in (minimum-1,minimum,minimum+10):
                with self.subTest(width=width,height=height):
                    output=pack_lines(options,width,height,2)
                    self.assertEqual(height>=minimum,output is not None)
                    if output:
                        self.assertEqual({0,1,2},set(output))
                        for e in output.values():
                            self.assertGreaterEqual(e['x'],0)
                            self.assertGreaterEqual(e['y'],0)
                            self.assertLessEqual(e['x']+e['width'],width+.0001)
                            self.assertLessEqual(e['y']+e['height'],height+.0001)
                        order=sorted(output,key=lambda i:(output[i]['y'],output[i]['x']))
                        self.assertEqual([0,1,2],order)
        self.assertEqual(original,options)

    def test_empty_infeasible_and_duplicate_leaves(self):
        self.assertIsNone(pack_lines([],100,100,2))
        self.assertIsNone(pack_lines([[leaf(0,101,20)]],100,100,2))
        self.assertIsNone(pack_lines([[leaf(0,20,20)],[]],100,100,2))
        with self.assertRaises(ValueError):
            pack_lines([[leaf(0,20,20)],[leaf(0,20,20)]],100,100,2)
        with self.assertRaises(ValueError):
            pack_lines([[leaf(0,20,20)],[leaf(0,20,20)]],20,100,2)
        with self.assertRaises(ValueError):
            pack_lines([[leaf(0,20,20),leaf(1,10,40)]],100,100,2)

    def test_width_reallocation_removes_a_line_without_shrinking(self):
        options=[[leaf(0,50,10),leaf(0,25,30)],[leaf(1,40,10)]]
        output=pack_lines(options,92,10,2)
        self.assertIsNotNone(output)
        self.assertEqual(50,output[0]['width'])
        self.assertEqual(10,output[0]['height'])


class MeasuredFlowTests(unittest.TestCase):
    def source(self):
        source=dict(canvas=dict(width=800,height=1000),elements=[])
        for i in range(3):
            source['elements'].append(dict(id='copy-'+str(i),type='text',x=50,y=100+i*250,
                width=700,height=150,content='Read every word and preserve the original message. '*3,
                font_family='Solstice Sans',font_size=24,color='rgba(0,0,0,1)'))
        return source

    def test_measured_copy_reflows_with_literal_content_and_no_ink_collisions(self):
        source=self.source();before=copy.deepcopy(source);target=dict(width=240,height=600)
        measurer=TextMeasurer();backgrounds=background_indices(source)
        candidates=list(flow_candidates(source,target,make_units(source,backgrounds),backgrounds,measurer))
        self.assertTrue(candidates)
        for method,design in candidates:
            self.assertFalse(validate_output(source,target,design))
            metrics=assess(source,design,backgrounds,measurer)
            self.assertGreaterEqual(metrics['minimum_font_size'],12)
            self.assertLessEqual(metrics['text_overflow_px'],.75)
            self.assertEqual(0,metrics['canvas_ink_overflow_px'])
            self.assertEqual(0,metrics['collision_proxy'])
            self.assertEqual([e['content'] for e in source['elements']],[e['content'] for e in design['elements']])
        self.assertEqual(before,source)

    def test_long_unbreakable_token_abstains_instead_of_editing_copy(self):
        source=self.source()
        for e in source['elements']:e['content']='W'*200
        candidates=list(flow_candidates(source,dict(width=80,height=400),make_units(source,[]),[],TextMeasurer()))
        self.assertEqual([],candidates)

    def test_ids_are_opaque_and_generation_is_deterministic(self):
        source=self.source();target=dict(width=240,height=600)
        def run(s):return list(flow_candidates(s,target,make_units(s,[]),[],TextMeasurer()))
        first=run(source)
        self.assertEqual(first,run(source))
        renamed=copy.deepcopy(source)
        for i,e in enumerate(renamed['elements']):e['id']='unrelated-'+str(i)
        second=run(renamed)
        for method,design in second:
            for i,e in enumerate(design['elements']):e['id']=source['elements'][i]['id']
        self.assertEqual(first,second)

    def test_supported_multitext_panel_reclaims_internal_whitespace(self):
        source=self.source()
        source['elements'].insert(0,dict(id='panel',type='shape',shape_type='rectangle',
            x=20,y=20,width=760,height=900,fill_color='rgba(255,255,255,1)',group_id=''))
        for e in source['elements'][1:]:e['group_id']=''
        target=dict(width=400,height=240);measurer=TextMeasurer()
        candidates=list(flow_candidates(source,target,make_units(source,[]),[],measurer))
        self.assertTrue(candidates)
        for _,design in candidates:
            self.assertFalse(validate_output(source,target,design))
            panel,*texts=design['elements']
            self.assertGreaterEqual(min(e['font_size'] for e in texts),12)
            self.assertTrue(all(a['y']+a['height']<b['y'] for a,b in zip(texts,texts[1:])))
            self.assertTrue(all(e['x']>=panel['x'] and e['y']>=panel['y'] and
                                e['x']+e['width']<=panel['x']+panel['width'] and
                                e['y']+e['height']<=panel['y']+panel['height'] for e in texts))

    def test_readable_layered_composition_keeps_aligned_brand_anchors(self):
        import json
        from pathlib import Path
        from engine.resize import resize_with_diagnostics
        root=Path(__file__).resolve().parents[1]
        source=json.loads((root/'tests/fixtures/hard-challenges/layered-contrast.json').read_text())['source']
        design,metrics=resize_with_diagnostics(source,dict(width=900,height=1200))
        logos=[e for e in design['elements'] if e['type']=='image' and 'logo' in e['asset_id']]
        self.assertEqual(2,len(logos))
        self.assertLess(abs(logos[0]['y']+logos[0]['height']/2-logos[1]['y']-logos[1]['height']/2),20)
        self.assertGreaterEqual(metrics['minimum_font_size'],12)

    def test_free_decoration_is_not_packed_as_reading_order_content(self):
        source=self.source()
        source['elements'].append(dict(id='decoration',type='shape',shape_type='ellipse',
            x=0,y=0,width=200,height=200,fill_color='rgba(0,0,0,.1)'))
        self.assertEqual([],list(flow_candidates(source,dict(width=400,height=240),
                                               make_units(source,[]),[],TextMeasurer())))

    def test_decorated_wide_headline_retains_a_wide_readable_slot(self):
        import json
        from pathlib import Path
        from engine.resize import resize_with_diagnostics
        root=Path(__file__).resolve().parents[1]
        source=json.loads((root/'input/chameleon_sample_level2_core.json').read_text())['source']
        design,metrics=resize_with_diagnostics(source,dict(width=1600,height=400))
        original=max((e for e in source['elements'] if e['type']=='text'),key=lambda e:e['font_size'])
        headline=next(e for e in design['elements'] if e['id']==original['id'])
        self.assertGreater(headline['width'],4*headline['height'])
        self.assertGreaterEqual(metrics['minimum_font_size'],12)
