"""Rendered regression controls, not independent aesthetic preference trials."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw
from engine.semantics import region_repairs, region_visibility, select_with_semantics, _CACHE
from engine.resize import evaluate_candidate, background_indices
from engine.measure import TextMeasurer
from engine.pixels import raster_diagnostics
from engine.validation import validate_output
from tests.test_semantics import FakeModel

FONTS=Path(__file__).resolve().parents[1]/'brand_kit/fonts'


def fixture(assets, kind='occlusion'):
    image=Image.new('RGBA',(100,100),(0,0,0,0))
    ImageDraw.Draw(image).rectangle((20,10,79,89),fill=(220,30,40,255))
    image.save(assets/'subject.png')
    source=dict(canvas=dict(width=240,height=200),elements=[
        dict(id='subject',type='image',asset_id='subject.png',fit='contain',x=70,y=50,width=100,height=100,z_index=0),
        dict(id='panel',type='shape',shape_type='rectangle',fill_color='rgba(0,0,0,1)',x=0,y=0,width=40,height=100,z_index=1)])
    baseline=deepcopy(source);baseline['elements'][1].update(x=100,y=50)
    if kind=='crop':
        source['elements']=source['elements'][:1];source['elements'][0]['fit']='cover'
        baseline=deepcopy(source);baseline['elements'][0].update(width=30,x=105)
    if kind=='group':
        source['elements'][1]['group_id']='panel'
        source['elements'].append(dict(id='decoration',type='shape',shape_type='rectangle',fill_color='rgba(255,255,255,1)',x=10,y=10,width=10,height=10,z_index=2,group_id='panel'))
        baseline=deepcopy(source)
        for e in baseline['elements'][1:]:e['x']+=100;e['y']+=50
    return source,baseline


def evaluator(source,assets):
    measurer=TextMeasurer(FONTS);backgrounds=background_indices(source)
    def evaluate(method,design):
        if validate_output(source,design['canvas'],design):return None
        score,quality=evaluate_candidate(source,design,backgrounds,measurer,assets)
        raster=raster_diagnostics(design,FONTS,assets)
        score-=2*raster['low_contrast_proxy']+.05*raster['busyness_proxy']
        return score,method,design,dict(quality,raster=raster,selection_score=score)
    return evaluate


class RegionRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.assets=Path(self.tmp.name);_CACHE.clear()
    def tearDown(self):self.tmp.cleanup()

    def test_generated_repairs_recover_visibility_with_real_quality_guards(self):
        for kind in ('occlusion','crop','group'):
            with self.subTest(kind=kind):
                source,baseline=fixture(self.assets,kind);before=deepcopy(baseline)
                evaluate=evaluator(source,self.assets);old=evaluate('baseline',baseline)
                model=FakeModel([])
                result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=model,evaluate=evaluate)
                self.assertEqual('selected',info['status'],info)
                self.assertEqual(0,model.calls)
                self.assertGreater(info['baseline_regions']['loss'],.3)
                accepted=[row for row in info['comparisons'] if row['accepted']]
                self.assertLess(accepted[-1]['regions']['loss'],.02)
                self.assertEqual([],validate_output(source,baseline['canvas'],result[2]))
                self.assertEqual(before,baseline)
                if kind=='group':
                    items={e['id']:e for e in result[2]['elements']}
                    self.assertEqual(10,items['decoration']['x']-items['panel']['x'])
                    self.assertEqual(10,items['decoration']['y']-items['panel']['y'])

    def test_source_intent_no_loss_means_no_proposals(self):
        source,baseline=fixture(self.assets);evaluate=evaluator(source,self.assets)
        old=evaluate('baseline',source)
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=FakeModel([]),evaluate=evaluate)
        self.assertIs(old,result);self.assertEqual(0,info['repair_proposals'])

    def test_off_does_not_evaluate_repairs(self):
        source,baseline=fixture(self.assets);old=evaluator(source,self.assets)('base',baseline)
        def fail(*args):raise AssertionError('off attempted repair')
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='off',evaluate=fail)
        self.assertIs(old,result)

    def test_bounds_budget_rotation_and_inferred_backing(self):
        source,baseline=fixture(self.assets)
        source['elements'].insert(0,dict(id='backing',type='shape',shape_type='rectangle',fill_color='rgba(255,255,255,1)',x=60,y=40,width=120,height=120,z_index=-1))
        baseline['elements'].insert(0,deepcopy(source['elements'][0]))
        annotations={'subject.png':dict(box=[.2,.1,.8,.9])}
        proposals=list(region_repairs(baseline,annotations,self.assets,limit=2,source=source))
        self.assertEqual(2,len(proposals))
        for _,out in proposals:
            self.assertEqual([],validate_output(source,out['canvas'],out))
            elements={e['id']:e for e in out['elements']}
            self.assertEqual(10,elements['subject']['x']-elements['backing']['x'])
            self.assertEqual(10,elements['subject']['y']-elements['backing']['y'])
        baseline['elements'][1]['rotation']=10
        self.assertEqual([],list(region_repairs(baseline,annotations,self.assets,source=source)))

    def test_empty_annotations_and_no_room_leave_no_candidates(self):
        source,baseline=fixture(self.assets)
        self.assertEqual([],list(region_repairs(baseline,{},self.assets)))
        baseline['elements'][1].update(x=0,y=0,width=240,height=200)
        self.assertEqual([],list(region_repairs(baseline,{'subject.png':dict(box=[.2,.1,.8,.9])},self.assets,source=source)))

    def test_one_subject_gain_is_not_diluted_by_unaffected_images(self):
        source,baseline=fixture(self.assets)
        for i in range(8):
            image=dict(source['elements'][0],id='peer'+str(i),x=i*27,y=175,width=20,height=20)
            source['elements'].append(deepcopy(image));baseline['elements'].append(image)
        evaluate=evaluator(source,self.assets);old=evaluate('baseline',baseline)
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=FakeModel([]),evaluate=evaluate)
        self.assertEqual('selected',info['status'],info)
        self.assertLess(info['baseline_regions']['loss'],.1)
        final=region_visibility(result[2],{'subject.png':dict(box=[.2,.1,.8,.9])},FONTS,self.assets)
        self.assertTrue(all(row['retained']>.98 for row in final['elements']))

    def test_repair_rejected_when_actual_guard_reports_regression(self):
        source,baseline=fixture(self.assets);evaluate=evaluator(source,self.assets)
        old=evaluate('baseline',baseline)
        def bad(method,design):
            row=evaluate(method,design)
            row[3]['missing_glyphs']=1
            return row
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=FakeModel([]),evaluate=bad)
        self.assertIs(old,result);self.assertGreater(info['repair_proposals'],0)
        self.assertFalse(any(row['accepted'] for row in info['comparisons']))

    def test_source_occlusion_is_not_repaired_as_an_error(self):
        _,baseline=fixture(self.assets);source=deepcopy(baseline)
        evaluate=evaluator(source,self.assets);old=evaluate('baseline',baseline)
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=FakeModel([]),evaluate=evaluate)
        self.assertIs(old,result);self.assertEqual(0,info['repair_proposals'])
