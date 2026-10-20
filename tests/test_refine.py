import copy
import unittest

from engine.measure import TextMeasurer
from engine.refine import refine_text
from engine.resize import make_units, assess
from engine.validation import validate_output


class TextRefinementTests(unittest.TestCase):
    def setUp(self):
        self.measurer=TextMeasurer()
        self.source=dict(canvas=dict(width=400,height=400),elements=[
            dict(id='a',type='text',content='Read this copy',font_family='Solstice Sans',
                 font_size=36,color='rgba(0,0,0,1)',x=20,y=20,width=350,height=60),
            dict(id='b',type='text',content='A second block stays below',font_family='Solstice Sans',
                 font_size=18,color='rgba(0,0,0,1)',x=20,y=250,width=350,height=100)])
        self.small=copy.deepcopy(self.source)
        for e in self.small['elements']:e['font_size']=6

    def run_refinement(self,source=None,design=None):
        source=source or self.source;design=design or self.small
        return refine_text(source,design,make_units(source,[]),[],self.measurer)

    def test_reclaims_space_without_changing_source_or_literal_style(self):
        before=copy.deepcopy(self.source);small=copy.deepcopy(self.small)
        result=self.run_refinement()
        self.assertIsNotNone(result)
        self.assertEqual([36,18],[e['font_size'] for e in result['elements']])
        self.assertEqual([],validate_output(self.source,self.small['canvas'],result))
        self.assertEqual(before,self.source);self.assertEqual(small,self.small)

    def test_preserves_left_center_and_right_alignment_anchors(self):
        for align in ('left','center','right'):
            source=copy.deepcopy(self.source);design=copy.deepcopy(self.small)
            for e in source['elements']+design['elements']:e['text_align']=align
            result=self.run_refinement(source,design)
            self.assertIsNotNone(result)
            factor={'left':0,'center':.5,'right':1}[align]
            for a,b in zip(design['elements'],result['elements']):
                self.assertAlmostEqual(a['x']+factor*a['width'],b['x']+factor*b['width'])
                self.assertEqual(a['y'],b['y'])

    def test_obstacles_do_not_gain_collisions_clipping_or_inversions(self):
        source=copy.deepcopy(self.source);design=copy.deepcopy(self.small)
        obstacle=dict(id='obstacle',type='shape',shape_type='rectangle',fill_color='rgba(255,0,0,1)',
                      x=20,y=90,width=360,height=100)
        source['elements'].append(obstacle);design['elements'].append(copy.deepcopy(obstacle))
        before=assess(source,design,[],self.measurer)
        result=self.run_refinement(source,design)
        self.assertIsNotNone(result)
        after=assess(source,result,[],self.measurer)
        for key in ('collision_proxy','text_overflow_px','canvas_ink_overflow_px','missing_glyphs','hierarchy_inversion'):
            self.assertLessEqual(after[key],before[key]+1e-6)
        self.assertEqual(obstacle,result['elements'][-1])

    def test_groups_rotation_and_search_budget_abstain(self):
        for mode in ('group','rotation','budget'):
            source=copy.deepcopy(self.source);design=copy.deepcopy(self.small)
            if mode=='budget':
                source['elements']=[dict(source['elements'][0],id=str(i)) for i in range(25)]
                design['elements']=[dict(design['elements'][0],id=str(i)) for i in range(25)]
            else:
                for e in source['elements']+design['elements']:e.update({'group_id':'g'} if mode=='group' else {'rotation':20})
            self.assertIsNone(self.run_refinement(source,design))

    def test_deterministic_and_identifier_invariant(self):
        a=self.run_refinement();self.assertEqual(a,self.run_refinement())
        source=copy.deepcopy(self.source);design=copy.deepcopy(self.small)
        for i,(s,d) in enumerate(zip(source['elements'],design['elements'])):s['id']=d['id']='renamed-'+str(i)
        b=self.run_refinement(source,design)
        for i,e in enumerate(b['elements']):e['id']=a['elements'][i]['id']
        self.assertEqual(a,b)

    def test_already_full_size_has_no_forced_rewrite(self):
        self.assertIsNone(self.run_refinement(design=self.source))

    def test_existing_backing_can_reflow_without_adding_a_panel(self):
        source=copy.deepcopy(self.source);design=copy.deepcopy(self.small)
        panel=dict(id='panel',type='shape',shape_type='rectangle',fill_color='rgba(0,0,0,1)',
                   x=20,y=100,width=350,height=100,group_id='panel-group',z_index=0)
        text=dict(id='inside',type='text',content='This supported paragraph can grow.',font_family='Solstice Sans',
                  font_size=24,color='rgba(255,255,255,1)',x=30,y=110,width=330,height=60,group_id='panel-group',z_index=1)
        source['elements']+=[panel,text]
        design['elements']+=[copy.deepcopy(panel),dict(text,font_size=6)]
        original=copy.deepcopy(design)
        result=self.run_refinement(source,design)
        self.assertIsNotNone(result)
        self.assertEqual([],validate_output(source,design['canvas'],result))
        self.assertGreaterEqual(result['elements'][-1]['font_size'],12)
        back,copy_block=result['elements'][-2:]
        self.assertGreaterEqual(copy_block['x'],back['x'])
        self.assertGreaterEqual(copy_block['y'],back['y'])
        self.assertLessEqual(copy_block['x']+copy_block['width'],back['x']+back['width'])
        self.assertLessEqual(copy_block['y']+copy_block['height'],back['y']+back['height'])
        self.assertEqual(original,design)
        # When no text can grow, a narrower backing alone is not a refinement.
        full=copy.deepcopy(source)
        full['elements'][-1]['x']+=4
        self.assertIsNone(self.run_refinement(source,full))

    def test_bottom_anchor_reclaims_space_above_footer(self):
        source=copy.deepcopy(self.source)
        source['elements']=[dict(source['elements'][0],content='Footer copy',x=20,y=300,width=350,height=80,font_size=30)]
        design=copy.deepcopy(source)
        design['elements'][0].update(y=380,height=15,font_size=6)
        before=copy.deepcopy(design)
        result=self.run_refinement(source,design)
        self.assertIsNotNone(result)
        e=result['elements'][0]
        self.assertGreater(e['font_size'],6)
        self.assertLess(e['y'],380)
        self.assertAlmostEqual(e['y']+e['height'],395)
        self.assertEqual(before,design)
        self.assertEqual([],validate_output(source,design['canvas'],result))

    def test_bottom_growth_does_not_cross_overlapping_neighbor(self):
        source=copy.deepcopy(self.source)
        source['elements'][0].update(y=380,height=15,font_size=30,content='Footer copy')
        source['elements'][1].update(y=330,height=40,font_size=18,content='Keep this row above')
        design=copy.deepcopy(source);design['elements'][0]['font_size']=6
        before=assess(source,design,[],self.measurer)
        result=self.run_refinement(source,design)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result['elements'][0]['y'],370)
        after=assess(source,result,[],self.measurer)
        self.assertLessEqual(after['collision_proxy'],before['collision_proxy']+1e-6)
        self.assertEqual(design['elements'][1],result['elements'][1])

    def test_missing_glyph_recovery_keeps_layout_and_exposes_missing_characters(self):
        from engine.refine import recover_missing_text
        source=copy.deepcopy(self.source)
        source['elements'][1].update(content='Readable Latin / 東京',font_size=18)
        design=copy.deepcopy(source);design['elements'][1]['font_size']=1
        original=copy.deepcopy(design)
        result=recover_missing_text(source,design,[],self.measurer)
        self.assertIsNotNone(result)
        self.assertGreater(result['elements'][1]['font_size'],1)
        self.assertGreater(self.measurer.measure(result['elements'][1]).missing_glyphs,0)
        self.assertEqual(result['elements'][0],original['elements'][0])
        for key in original['elements'][1]:
            if key!='font_size':self.assertEqual(original['elements'][1][key],result['elements'][1][key])
        self.assertEqual(original,design)

    def test_glyph_recovery_abstains_when_fit_is_impossible_or_glyphs_are_complete(self):
        from engine.refine import recover_missing_text
        self.assertIsNone(recover_missing_text(self.source,self.small,[],self.measurer))
        source=copy.deepcopy(self.source)
        source['elements'][1].update(content='東京'*30,width=1,height=1,font_size=18)
        design=copy.deepcopy(source);design['elements'][1]['font_size']=1
        self.assertIsNone(recover_missing_text(source,design,[],self.measurer))
