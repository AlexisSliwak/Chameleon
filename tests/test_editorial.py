"""Editorial candidates: conservation, optical prominence and scope boundaries."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import unittest

from engine.editorial import editorial_candidates, visible_fraction
from engine.measure import TextMeasurer
from engine.validation import validate_output

ROOT=Path(__file__).resolve().parents[1]
EDITABLE={'x','y','width','height','font_size'}


class EditorialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.measure=TextMeasurer()

    def source(self,name):
        return json.loads((ROOT/'input'/name).read_text())

    def assert_preserved(self,source,target,design):
        self.assertEqual([],validate_output(source,target,design))
        self.assertEqual(Counter(e['id'] for e in source['elements']),Counter(e['id'] for e in design['elements']))
        for before,after in zip(source['elements'],design['elements']):
            self.assertEqual({k:v for k,v in before.items() if k not in EDITABLE},
                             {k:v for k,v in after.items() if k not in EDITABLE})

    def test_sample_contracts_and_no_input_mutation(self):
        for path in sorted((ROOT/'input').glob('*.json')):
            task=json.loads(path.read_text());source=task['source'];before=deepcopy(source)
            for target in (task['target_canvas'],dict(width=1080,height=1350)):
                with self.subTest(path=path.name,target=target):
                    candidates=list(editorial_candidates(source,target,self.measure))
                    self.assertTrue(candidates)
                    for method,design in candidates:self.assert_preserved(source,target,design)
            self.assertEqual(before,source)

    def test_renaming_ids_and_groups_does_not_change_composition(self):
        task=self.source('chameleon_sample_level2_core.json');source=task['source'];changed=deepcopy(source)
        mapping={e['id']:'opaque-'+str(i) for i,e in enumerate(source['elements'])}
        for element in changed['elements']:
            element['id']=mapping[element['id']]
            if element.get('group_id') is not None:element['group_id']='opaque-group-'+str(list(mapping).index(next(e['id'] for e in source['elements'] if e.get('group_id')==element['group_id'])))
        expected=list(editorial_candidates(source,task['target_canvas'],self.measure))
        actual=list(editorial_candidates(changed,task['target_canvas'],self.measure))
        self.assertEqual([x[0] for x in expected],[x[0] for x in actual])
        for (_,a),(_,b) in zip(expected,actual):
            self.assertEqual([{k:v for k,v in e.items() if k in EDITABLE} for e in a['elements']],
                             [{k:v for k,v in e.items() if k in EDITABLE} for e in b['elements']])

    def test_core_hero_remains_prominent_and_action_subordinate(self):
        task=self.source('chameleon_sample_level2_core.json')
        for _,design in editorial_candidates(task['source'],task['target_canvas'],self.measure):
            # Identify the source's largest non-background square image without
            # relying on sample role IDs in the implementation.
            images=[(i,e) for i,e in enumerate(task['source']['elements']) if e['type']=='image' and e.get('fit')!='cover']
            index=max(images,key=lambda item:item[1]['width']*item[1]['height'])[0]
            hero=design['elements'][index];l,t,r,b=visible_fraction(hero,ROOT/'brand_kit/assets')
            self.assertGreater(hero['height']*(b-t),task['target_canvas']['height']*.55)
            texts=[e for e in design['elements'] if e['type']=='text']
            headline=max(texts,key=lambda e:e['font_size'])
            group_labels=[e for e in texts if e.get('group_id') is not None]
            self.assertGreater(headline['font_size'],max(e['font_size'] for e in group_labels)*1.5)

    def test_dense_rotated_lockup_not_reduced_to_two_pixel_type(self):
        task=self.source('chameleon_sample_level3_advanced.json')
        design=list(editorial_candidates(task['source'],task['target_canvas'],self.measure))[0][1]
        rotated=[e for e in design['elements'] if e['type']=='text' and e.get('rotation')]
        self.assertTrue(rotated)
        self.assertGreaterEqual(min(e['font_size'] for e in rotated),6)
        self.assert_preserved(task['source'],task['target_canvas'],design)

    def test_unsupported_compound_cards_are_not_demoted_to_footer(self):
        source=dict(canvas=dict(width=900,height=700),elements=[
            dict(id='title',type='text',x=30,y=20,width=800,height=90,content='A collection',font_family='Solstice Sans',font_size=45,color='black'),
            dict(id='card-art',type='image',x=40,y=150,width=200,height=300,asset_id='solstice_bottle.png',group_id='card'),
            dict(id='card-copy',type='text',x=40,y=460,width=200,height=80,content='Product details',font_family='Solstice Sans',font_size=20,color='black',group_id='card')])
        self.assertEqual([],list(editorial_candidates(source,dict(width=1200,height=500),self.measure)))

    def test_ungrouped_contrast_support_panel_is_not_decoration(self):
        source=dict(canvas=dict(width=900,height=700),elements=[
            dict(id='title',type='text',x=30,y=20,width=800,height=90,content='A collection',font_family='Solstice Sans',font_size=45,color='black'),
            dict(id='panel',type='shape',x=40,y=150,width=600,height=350,shape_type='rectangle',fill_color='black',z_index=1),
            dict(id='copy',type='text',x=70,y=200,width=520,height=180,content='White on dark support',font_family='Solstice Sans',font_size=20,color='white',z_index=2)])
        self.assertEqual([],list(editorial_candidates(source,dict(width=1200,height=500),self.measure)))


    def test_zero_or_rotated_image_abstains_without_crashing(self):
        task=self.source('chameleon_sample_level1_warmup.json')
        for edits in ({'width':0},{'height':0},{'rotation':15}):
            source=deepcopy(task['source'])
            image=next(e for e in source['elements'] if e['type']=='image' and e.get('fit')!='cover')
            image.update(edits)
            self.assertEqual([],list(editorial_candidates(source,task['target_canvas'],self.measure)))


    def test_multiple_legal_units_abstain_instead_of_overlapping(self):
        task=self.source('chameleon_sample_level3_advanced.json')
        source=deepcopy(task['source'])
        footer=deepcopy(min((e for e in source['elements'] if e['type']=='text'),
                            key=lambda e:e['font_size']))
        footer.update(id='second-independent-disclaimer',content='Additional conditions apply.',y=1280.)
        source['elements'].append(footer)
        for target in (task['target_canvas'],dict(width=1080,height=1350),dict(width=1600,height=400)):
            with self.subTest(target=target):
                self.assertEqual([],list(editorial_candidates(source,target,self.measure)))


if __name__=='__main__':unittest.main()
