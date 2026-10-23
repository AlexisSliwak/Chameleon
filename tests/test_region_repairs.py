"""Rendered regression controls, not independent aesthetic preference trials."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import os
from unittest.mock import patch
from PIL import Image, ImageDraw
from engine.semantics import region_repairs, region_visibility, select_with_semantics, prepare_region_pool, _CACHE
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

    def test_early_pool_can_repair_a_seed_outside_the_existing_shortlist(self):
        source,seed=fixture(self.assets);evaluate=evaluator(source,self.assets)
        blocked=deepcopy(seed);blocked['elements'][1].update(x=0,y=0,width=240,height=200)
        original=evaluate('incumbent',blocked);seed_row=evaluate('source-fit',seed)
        model=FakeModel([]);snapshot=deepcopy(source)
        with patch.dict(os.environ,{'CHAMELEON_ADVISOR':'regions'}),patch('engine.semantics.get_model',return_value=model):
            proposals,context=prepare_region_pool(source,[seed_row],FONTS,self.assets)
        self.assertGreater(len(proposals),0);self.assertLessEqual(len(proposals),16)
        guided=[evaluate(method,d) for method,d in proposals]
        result,info=select_with_semantics(source,original,[],FONTS,self.assets,mode='regions',model=model,
            evaluate=evaluate,context=context,guided=guided)
        self.assertEqual('selected',info['status'],info)
        self.assertEqual(snapshot,source)
        self.assertEqual(0,model.calls)
        observed=region_visibility(result[2],context['annotations'],FONTS,self.assets)
        self.assertGreater(observed['elements'][0]['retained'],.98)

    def test_background_subject_moves_occluder_not_background(self):
        source,baseline=fixture(self.assets)
        source['elements'][0].update(x=0,y=0,width=240,height=200,fit='cover')
        source['elements'][1].update(x=0,y=0,width=40,height=100)
        baseline=deepcopy(source);baseline['elements'][1].update(x=100,y=50)
        evaluate=evaluator(source,self.assets);old=evaluate('source-fit',baseline)
        with patch.dict(os.environ,{'CHAMELEON_ADVISOR':'regions'}),patch('engine.semantics.get_model',return_value=FakeModel([])):
            proposals,context=prepare_region_pool(source,[old],FONTS,self.assets)
        self.assertTrue(proposals)
        for _,d in proposals:self.assertEqual(baseline['elements'][0],d['elements'][0])
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=FakeModel([]),evaluate=evaluate,
            context=context,guided=[evaluate(m,d) for m,d in proposals])
        self.assertEqual('selected',info['status'],info)
        self.assertEqual(baseline['elements'][0],result[2]['elements'][0])

    def test_preparation_off_and_failed_inference_preserve_incumbent(self):
        source,baseline=fixture(self.assets);old=evaluator(source,self.assets)('base',baseline)
        with patch.dict(os.environ,{'CHAMELEON_ADVISOR':'off'}),patch('engine.semantics.get_model') as model:
            self.assertEqual(([],None),prepare_region_pool(source,[old],FONTS,self.assets));model.assert_not_called()
        Image.new('RGB',(100,100),'red').save(self.assets/'subject.png')
        from engine.local_model import ModelUnavailable
        model=FakeModel([ModelUnavailable('unavailable')])
        with patch.dict(os.environ,{'CHAMELEON_ADVISOR':'regions'}),patch('engine.semantics.get_model',return_value=model):
            proposals,context=prepare_region_pool(source,[old],FONTS,self.assets)
        self.assertEqual([],proposals);self.assertEqual('fallback',context['status'])
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=model,context=context)
        self.assertIs(old,result);self.assertEqual(1,info['model_calls'])

    def test_early_proposal_render_failure_retains_incumbent(self):
        source,seed=fixture(self.assets);evaluate=evaluator(source,self.assets);old=evaluate('source-fit',seed)
        model=FakeModel([])
        with patch.dict(os.environ,{'CHAMELEON_ADVISOR':'regions'}),patch('engine.semantics.get_model',return_value=model):
            proposals,context=prepare_region_pool(source,[old],FONTS,self.assets)
        self.assertTrue(proposals)
        def broken(*args):raise OSError('proposal renderer unavailable')
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=model,
            evaluate=broken,context=context,proposals=proposals)
        self.assertIs(old,result);self.assertEqual('fallback',info['status'])
        self.assertIn('proposal renderer unavailable',info['reason'])

    def test_zero_loss_skips_proposal_evaluation_and_preserves_source_diagnostics(self):
        source,_=fixture(self.assets);evaluate=evaluator(source,self.assets);old=evaluate('source-fit',source)
        def fail(*args):raise AssertionError('cannot improve zero introduced loss')
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=FakeModel([]),
            evaluate=fail,proposals=[('unused',deepcopy(source))])
        self.assertIs(old,result);self.assertEqual('no_recoverable_loss',info['short_circuit'])
        self.assertEqual(0,info['baseline_regions']['loss'])

    def test_visibility_cache_preserves_source_occlusion_diagnostics(self):
        _,source=fixture(self.assets);evaluate=evaluator(source,self.assets);old=evaluate('source-fit',source)
        result,info=select_with_semantics(source,old,[],FONTS,self.assets,mode='regions',model=FakeModel([]),evaluate=evaluate)
        self.assertIs(old,result)
        self.assertGreater(info['source_regions']['loss'],.5)
        self.assertEqual(0,info['baseline_regions']['loss'])
