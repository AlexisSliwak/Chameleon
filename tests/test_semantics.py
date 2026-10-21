import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from deployment.fetch_model import fetch, download_ranges
from engine.local_model import LocalModel, ModelUnavailable
from engine.semantics import (validate_region, annotate_assets, region_visibility,
                              compare_layouts, safe_challenger, select_with_semantics, check_render_budget, _preview, _CACHE)

ROOT=Path(__file__).resolve().parents[1]

class FakeModel:
    def __init__(self, replies): self.replies=iter(replies); self.calls=0; self.seconds=0.; self.identity=object()
    def ask(self,*args,**kwargs):
        self.calls+=1
        value=next(self.replies)
        if isinstance(value,Exception): raise value
        return value


def design():
    return dict(canvas=dict(width=200,height=200),elements=[
        dict(id='art',type='image',asset_id='art.png',fit='contain',x=50,y=50,width=100,height=100,z_index=0)])


def candidate(d,method='base'):
    quality={k:0 for k in ('text_overflow_px','canvas_ink_overflow_px','missing_glyphs','collision_proxy','hierarchy_inversion')}
    quality.update(minimum_font_size=12,raster=dict(low_contrast_proxy=0,sampled_low_contrast_proxy=0),
                   composition=dict(copy_floor_loss=0,hierarchy_loss=0,peer_order_loss=0,hero_retention=1))
    return (1,method,d,quality)

class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.assets=Path(self.temp.name)
        Image.new('RGBA',(100,100),'red').save(self.assets/'art.png')
        self.fonts=ROOT/'brand_kit/fonts';self.source=design();_CACHE.clear()
    def tearDown(self):self.temp.cleanup()

    def test_region_rejects_malformed_nonfinite_tiny_and_outside(self):
        for value in (None,{},dict(kind='person',box=[0,0,1,1]),dict(kind='subject',box=[0,0,float('nan'),1]),
                      dict(kind='subject',box=[0,0,True,1]),dict(kind='subject',box=[-1,0,1,1]),
                      dict(kind='logo',box=[.1,.1,.11,.11]),dict(kind='none',box=[0,0,0,0])):
            self.assertIsNone(validate_region(value))
        self.assertEqual('logo',validate_region(dict(kind='logo',box=[0,0,1,1]))['kind'])

    def test_cache_uses_content_model_and_abstentions(self):
        m=FakeModel([dict(kind='none',box=[0,0,0,0])]*2)
        annotate_assets(self.source,self.assets,m);annotate_assets(self.source,self.assets,m)
        self.assertEqual(1,m.calls)
        Image.new('RGBA',(100,100),'blue').save(self.assets/'art.png')
        annotate_assets(self.source,self.assets,m);self.assertEqual(2,m.calls)
        other=FakeModel([dict(kind='subject',box=[0,0,1,1])])
        annotations,_=annotate_assets(self.source,self.assets,other)
        self.assertIn('art.png',annotations);self.assertEqual(1,other.calls)

    def test_invalid_region_is_failure_not_permission_to_ignore_subjects(self):
        model=FakeModel([dict(kind='subject',box=[-1,0,1,1])])
        with self.assertRaises(ModelUnavailable):annotate_assets(self.source,self.assets,model)
        self.assertFalse(_CACHE)

    def test_raster_budget_rejects_large_source_before_conversion(self):
        source=copy.deepcopy(self.source);source['canvas']=dict(width=100000,height=100000)
        with patch('engine.semantics.convert_chameleon_to_crello') as convert:
            with self.assertRaises(ModelUnavailable):_preview(source,self.fonts,self.assets)
            with self.assertRaises(ModelUnavailable):region_visibility(source,{},self.fonts,self.assets)
            convert.assert_not_called()
        old=candidate(self.source);new_design=copy.deepcopy(self.source);new_design['elements'][0]['x']=60
        result,info=select_with_semantics(source,old,[candidate(new_design,'new')],self.fonts,self.assets,model=FakeModel([]),mode='both')
        self.assertIs(old,result);self.assertEqual('fallback',info['status'])

    def test_cover_intermediate_budget_precedes_allocation(self):
        Image.new('RGBA',(10000,1),'red').save(self.assets/'art.png')
        source=copy.deepcopy(self.source);source['elements'][0].update(width=200,height=200,fit='cover')
        with self.assertRaisesRegex(ModelUnavailable,'cover raster'):check_render_budget(source,self.assets)

    def test_partial_bleed_is_not_mistaken_for_full_canvas_background(self):
        source=copy.deepcopy(self.source);source['elements'][0].update(x=-100,y=0,width=200,height=200,fit='cover')
        model=FakeModel([dict(kind='subject',box=[0,0,1,1])])
        annotations,_=annotate_assets(source,self.assets,model)
        self.assertIn('art.png',annotations)
        source['elements'][0]['x']=0
        annotations,_=annotate_assets(source,self.assets,model)
        self.assertFalse(annotations);self.assertEqual(1,model.calls)

    def test_abstention_ignores_unused_box_but_rejects_nonfinite_values(self):
        model=FakeModel([dict(kind='none',box=[0,0,1,1])])
        regions,trace=annotate_assets(self.source,self.assets,model)
        self.assertFalse(regions);self.assertEqual('abstained',trace['assets'][0]['status'])
        model=FakeModel([dict(kind='none',box=[0,0,float('nan'),1])])
        with self.assertRaises(ModelUnavailable):annotate_assets(self.source,self.assets,model)

    def test_alpha_support_protects_white_lettering_without_inference(self):
        image=Image.new('RGBA',(100,100),(0,0,0,0))
        for x in range(40,60):
            for y in range(40,60):image.putpixel((x,y),(255,255,255,255))
        image.save(self.assets/'art.png');model=FakeModel([])
        regions,trace=annotate_assets(self.source,self.assets,model)
        self.assertEqual([.4,.4,.6,.6],regions['art.png']['box'])
        self.assertEqual('alpha-support',trace['assets'][0]['method']);self.assertEqual(0,model.calls)
        regions,trace=annotate_assets(self.source,self.assets,model)
        self.assertTrue(trace['assets'][0]['cache_hit']);self.assertEqual('alpha-support',trace['assets'][0]['method'])

    def test_asset_budget_and_missing_asset(self):
        self.source['elements']=[]
        for n in range(6):
            e=design()['elements'][0];e.update(id=str(n),asset_id=str(n)+'.png');self.source['elements'].append(e)
            if n:Image.new('RGB',(20,20),(n*30,0,0)).save(self.assets/e['asset_id'])
        m=FakeModel([dict(kind='none',box=[0,0,0,0])]*3)
        _,trace=annotate_assets(self.source,self.assets,m)
        self.assertEqual(3,m.calls);self.assertEqual(2,len(trace['omitted_assets']))
        self.assertEqual('missing',trace['assets'][0]['status'])

    def visibility(self,d,box=None):
        return region_visibility(d,{'art.png':dict(box=box or [0,0,1,1])},self.fonts,self.assets)['elements'][0]

    def test_actual_occlusion_and_transparent_layer(self):
        before=copy.deepcopy(self.source)
        self.assertAlmostEqual(1,self.visibility(self.source)['retained'],places=3)
        cover=dict(id='cover',type='shape',shape_type='rectangle',fill_color='rgba(0,0,0,1)',x=50,y=50,width=100,height=100,z_index=1)
        d=copy.deepcopy(self.source);d['elements'].append(cover)
        self.assertLess(self.visibility(d)['retained'],.01)
        cover['fill_color']='rgba(0,0,0,0)'
        self.assertGreater(self.visibility(d)['retained'],.99)
        self.assertEqual(before,self.source)

    def test_rotation_and_contain_letterboxing(self):
        d=copy.deepcopy(self.source);d['elements'][0].update(rotation=35,width=120,height=60)
        self.assertGreater(self.visibility(d)['retained'],.99)

    def test_cover_crop_counts_lost_subject(self):
        Image.new('RGBA',(200,100),'red').save(self.assets/'art.png')
        d=copy.deepcopy(self.source);d['elements'][0]['fit']='cover'
        result=self.visibility(d)
        self.assertAlmostEqual(.5,result['crop_fraction'],delta=.02)
        self.assertAlmostEqual(.5,result['retained'],delta=.02)
        self.assertLess(self.visibility(d,[0,0,.2,1])['retained'],.01)

    def test_transparent_subject_has_no_measurable_evidence(self):
        Image.new('RGBA',(100,100),(0,0,0,0)).save(self.assets/'art.png')
        self.assertFalse(self.visibility(self.source)['measurable'])

    def test_guard_rejects_independent_regressions_and_content_mutation(self):
        old=candidate(self.source)
        for section,key in ((None,'text_overflow_px'),(None,'missing_glyphs'),('raster','low_contrast_proxy'),('composition','copy_floor_loss')):
            new=copy.deepcopy(old)
            (new[3] if section is None else new[3][section])[key]=1
            self.assertFalse(safe_challenger(self.source,old,new,self.assets))
        new=copy.deepcopy(old);new[2]['elements'][0]['asset_id']='other.png'
        self.assertFalse(safe_challenger(self.source,old,new,self.assets))
        self.assertTrue(safe_challenger(self.source,old,old,self.assets))

    def compare(self,replies):
        with patch('engine.semantics._preview',return_value=Image.new('RGB',(10,10))):
            return compare_layouts(self.source,self.source,self.source,self.fonts,self.assets,FakeModel(replies))

    def test_preference_requires_reversed_order_and_matching_evidence(self):
        vote=lambda winner,issue='grouping':dict(winner=winner,issue=issue if winner in ('A','B') else 'none',element_ids=['art'] if winner in ('A','B') else [])
        self.assertTrue(self.compare([vote('B'),vote('A')])[0])
        for replies in ([vote('A'),vote('A')],[vote('B'),vote('B')],[vote('tie'),vote('tie')],[vote('B'),vote('A','hierarchy')]):
            self.assertFalse(self.compare(replies)[0])
        with self.assertRaises(ModelUnavailable):self.compare([dict(winner='B',issue='grouping',element_ids=['invented'])])
        self.assertFalse(self.compare([dict(winner='A',issue='none',element_ids=[])]*2)[0])

    def test_default_keeps_model_free_path_without_approval_assumption(self):
        old=candidate(self.source)
        with patch.dict('os.environ',{},clear=True),patch('engine.semantics.get_model') as get:
            result,info=select_with_semantics(self.source,old,[],self.fonts,self.assets)
        self.assertIs(old,result);self.assertEqual('disabled',info['status']);get.assert_not_called()

    def test_disabled_never_loads_and_failure_restores_incumbent(self):
        old=candidate(self.source);d=copy.deepcopy(self.source);d['elements'][0]['x']=55;new=candidate(d,'new')
        m=FakeModel([ModelUnavailable('failed')])
        result,info=select_with_semantics(self.source,old,[new],self.fonts,self.assets,model=m,mode='off')
        self.assertIs(old,result);self.assertEqual(0,m.calls)
        result,info=select_with_semantics(self.source,old,[new],self.fonts,self.assets,model=m,mode='both')
        self.assertIs(old,result);self.assertEqual('fallback',info['status'])

    def test_critic_selection_and_rollback_after_later_failure(self):
        old=candidate(self.source);d=copy.deepcopy(self.source);d['elements'][0]['x']=55;new=candidate(d,'new')
        vote=lambda winner:dict(winner=winner,issue='grouping',element_ids=['art'])
        with patch('engine.semantics._preview',return_value=Image.new('RGB',(10,10))):
            result,info=select_with_semantics(self.source,old,[new],self.fonts,self.assets,model=FakeModel([vote('B'),vote('A')]),mode='critic')
            self.assertIs(new,result);self.assertEqual('selected',info['status'])
            d2=copy.deepcopy(d);d2['elements'][0]['x']=60
            result,info=select_with_semantics(self.source,old,[new,candidate(d2)],self.fonts,self.assets,
                model=FakeModel([vote('B'),vote('A'),ModelUnavailable('late failure')]),mode='critic')
            self.assertIs(old,result);self.assertEqual('fallback',info['status'])

    def test_region_only_selection_improves_visible_subject(self):
        old_design=copy.deepcopy(self.source)
        old_design['elements'].append(dict(id='cover',type='shape',shape_type='rectangle',fill_color='rgba(0,0,0,1)',x=50,y=50,width=100,height=100,z_index=1))
        d=copy.deepcopy(old_design);d['elements'][-1].update(x=0,y=0,width=25,height=25)
        old=candidate(old_design);new=candidate(d,'new')
        result,info=select_with_semantics(d,old,[new],self.fonts,self.assets,
            model=FakeModel([dict(kind='subject',box=[0,0,1,1])]),mode='regions')
        self.assertIs(new,result);self.assertEqual('selected',info['status'])

    def test_regions_preserve_intentional_source_occlusion(self):
        source=copy.deepcopy(self.source)
        source['elements'].append(dict(id='cover',type='shape',shape_type='rectangle',fill_color='rgba(0,0,0,1)',x=50,y=50,width=100,height=100,z_index=1))
        d=copy.deepcopy(source);d['elements'][-1].update(x=0,y=0,width=25,height=25)
        old=candidate(source);new=candidate(d,'new')
        result,info=select_with_semantics(source,old,[new],self.fonts,self.assets,
            model=FakeModel([dict(kind='subject',box=[0,0,1,1])]),mode='regions')
        self.assertIs(old,result)
        self.assertEqual(0,info['baseline_regions']['loss'])

    def test_both_vetoes_subject_loss_before_asking_critic(self):
        source=copy.deepcopy(self.source)
        source['elements'].append(dict(id='cover',type='shape',shape_type='rectangle',fill_color='rgba(0,0,0,1)',x=0,y=0,width=25,height=25,z_index=1))
        blocked=copy.deepcopy(source);blocked['elements'][-1].update(x=50,y=50,width=100,height=100)
        old=candidate(source);model=FakeModel([dict(kind='subject',box=[0,0,1,1])])
        result,info=select_with_semantics(source,old,[candidate(blocked,'blocked')],self.fonts,self.assets,model=model,mode='both')
        self.assertIs(old,result);self.assertEqual(1,model.calls)
        self.assertEqual('region_regression',info['comparisons'][0]['reason'])

    def test_design_budget_skips_inference(self):
        source=copy.deepcopy(self.source)
        source['elements']=[dict(source['elements'][0],id=str(n)) for n in range(65)]
        old=candidate(source);model=FakeModel([])
        result,info=select_with_semantics(source,old,[],self.fonts,self.assets,model=model,mode='both')
        self.assertIs(old,result);self.assertEqual('budget_abstention',info['status']);self.assertEqual(0,model.calls)

class ArtifactTests(unittest.TestCase):
    def test_download_verify_cache_and_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);data=b'model';manifest=dict(files=[dict(name='model.gguf',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),url='https://example.invalid')])
            with patch('deployment.fetch_model.urllib.request.urlopen',return_value=BytesIO(data)) as get:
                fetch(manifest,root);fetch(manifest,root);self.assertEqual(1,get.call_count)
            self.assertEqual(manifest,json.loads((root/'manifest.json').read_text()))
            (root/'model.gguf').write_bytes(b'corrupt')
            with patch('deployment.fetch_model.urllib.request.urlopen',return_value=BytesIO(b'bad')):
                with self.assertRaises(ValueError):fetch(manifest,root)
            self.assertFalse((root/'model.gguf.partial').exists())
            self.assertEqual(b'corrupt',(root/'model.gguf').read_bytes())
    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):fetch(dict(files=[dict(name='../escape')]),Path(temp))
    def test_runtime_failure_circuit(self):
        model=LocalModel()
        with patch.object(model,'start',side_effect=ModelUnavailable('absent')):
            with self.assertRaises(ModelUnavailable):model.ask('',[],{})
        self.assertEqual('absent',model.failure)
        with self.assertRaises(ModelUnavailable):model.start()

    def test_runtime_strict_response_and_loopback_payload(self):
        model=LocalModel();model.url='http://127.0.0.1:12345'
        good={'choices':[{'finish_reason':'stop','message':{'content':'{"kind":"none","box":[0,0,0,0]}'}}]}
        with patch.object(model,'start'),patch.object(model.http,'open',return_value=BytesIO(json.dumps(good).encode())) as post:
            value=model.ask('inspect',[Image.new('RGB',(2,2))],{'type':'object'})
            self.assertEqual('none',value['kind'])
            request=post.call_args.args[0];payload=json.loads(request.data)
            self.assertTrue(request.full_url.startswith('http://127.0.0.1:'))
            self.assertTrue(payload['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,'))
            self.assertFalse(payload['chat_template_kwargs']['enable_thinking'])
        for body in ({'choices':[]},{'choices':[None]}, {'choices':[{'finish_reason':'length'}]}, {'choices':[{'finish_reason':'stop','message':{'content':'not JSON'}}]}):
            model=LocalModel();model.url='http://127.0.0.1:12345'
            with patch.object(model,'start'),patch.object(model.http,'open',return_value=BytesIO(json.dumps(body).encode())):
                with self.assertRaises(ModelUnavailable):model.ask('',[],{})
            self.assertIsNotNone(model.failure)

    def test_model_identity_tracks_manifest_change(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict('os.environ',{'CHAMELEON_MODEL_DIR':temp}):
            p=Path(temp)/'manifest.json';p.write_text('one');model=LocalModel();before=model.identity
            p.write_text('two');self.assertNotEqual(before,model.identity)

    def test_parallel_ranges_assemble_in_order(self):
        data=b'abcdefghij'
        def response(request,timeout):
            start,end=map(int,request.get_header('Range').removeprefix('bytes=').split('-'))
            result=BytesIO(data[start:end+1]);result.status=206
            result.headers={'Content-Range':f'bytes {start}-{end}/{len(data)}'}
            return result
        with tempfile.TemporaryDirectory() as temp,patch('deployment.fetch_model.urllib.request.urlopen',side_effect=response):
            target=Path(temp)/'model.partial'
            download_ranges(dict(url='https://example.invalid',bytes=len(data),name='model'),target,chunk_size=3,workers=3)
            self.assertEqual(data,target.read_bytes())
            self.assertEqual([target],list(Path(temp).iterdir()))

    def test_parallel_ranges_reject_ignored_range_and_truncation(self):
        for status,body in [(200,b'abcd'),(206,b'a')]:
            def response(request,timeout):
                result=BytesIO(body);result.status=status;result.headers={'Content-Range':'bytes 0-3/4'};return result
            with tempfile.TemporaryDirectory() as temp,patch('deployment.fetch_model.urllib.request.urlopen',side_effect=response):
                target=Path(temp)/'model.partial'
                with self.assertRaises(ValueError):download_ranges(dict(url='https://example.invalid',bytes=4,name='model'),target,chunk_size=4)
                self.assertEqual([],list(Path(temp).iterdir()))

    def test_image_labels_precede_their_corresponding_pixels(self):
        model=LocalModel();model.url='http://127.0.0.1:12345'
        good={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        with patch.object(model,'start'),patch.object(model.http,'open',return_value=BytesIO(json.dumps(good).encode())) as post:
            model.ask('compare',[Image.new('RGB',(2,2)),Image.new('RGB',(3,3))],{},labels=['A','B'])
            content=json.loads(post.call_args.args[0].data)['messages'][1]['content']
            self.assertEqual(['text','text','image_url','text','image_url'],[part['type'] for part in content])
            self.assertEqual('A',content[1]['text']);self.assertEqual('B',content[3]['text'])
