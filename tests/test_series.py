"""Repeated cards retain narrative order and proportional art at new ratios."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from engine.measure import TextMeasurer
from engine.series import series_candidates
from engine.validation import validate_output
from engine.editorial import visible_fraction

ROOT=Path(__file__).resolve().parents[1]


class SeriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.measurer=TextMeasurer()
        cls.source=json.loads((ROOT/'tests/fixtures/design-families/commerce-triptych.json').read_text())['source']

    def test_order_conservation_and_consistent_cards_across_ratios(self):
        for W,H in [(600,1200),(1080,1080),(1200,628)]:
            with self.subTest(target=(W,H)):
                source=deepcopy(self.source);before=deepcopy(source)
                candidates=list(series_candidates(source,dict(width=W,height=H),self.measurer))
                self.assertTrue(candidates)
                for _,design in candidates:
                    self.assertEqual([],validate_output(source,dict(width=W,height=H),design))
                    elems={e['id']:e for e in design['elements']}
                    cards=[elems['product-'+str(i)+'-card'] for i in range(3)]
                    self.assertEqual(1,len({(e['width'],e['height']) for e in cards}))
                    if H/W>1.3:self.assertTrue(all(a['y']+a['height']<=b['y'] for a,b in zip(cards,cards[1:])))
                    else:self.assertTrue(all(a['x']+a['width']<=b['x'] for a,b in zip(cards,cards[1:])))
                    for i,card in enumerate(cards):
                        art=elems['product-'+str(i)+'-image']
                        l,t,r,b=visible_fraction(art,ROOT/'brand_kit/assets')
                        text=elems['product-'+str(i)+'-name']
                        if H/W>1.3:self.assertLessEqual(art['x']+art['width']*r,text['x'])
                        else:self.assertLessEqual(art['y']+art['height']*b,text['y'])
                    last=max(e['y']+e['height'] for e in cards)
                    self.assertGreater(elems['action-plate']['y'],last)
                    self.assertGreater(elems['terms']['y'],last)
                    self.assertLess(elems['headline']['y']+elems['headline']['height'],min(e['y'] for e in cards))
                    # Same source role sizes remain the same across cards.
                    for suffix in ('name','detail','price'):
                        self.assertEqual(1,len({elems['product-'+str(i)+'-'+suffix]['font_size'] for i in range(3)}))
                self.assertEqual(before,source)

    def test_id_and_group_renaming_is_geometry_invariant(self):
        renamed=deepcopy(self.source);groups={}
        for i,e in enumerate(renamed['elements']):
            e['id']='node-'+str(i)
            if e.get('group_id') is not None:
                groups.setdefault(e['group_id'],'group-'+str(len(groups)))
                e['group_id']=groups[e['group_id']]
        target=dict(width=600,height=1200)
        a=list(series_candidates(self.source,target,self.measurer))[0][1]
        b=list(series_candidates(renamed,target,self.measurer))[0][1]
        fields=('x','y','width','height','font_size')
        self.assertEqual([[e.get(k) for k in fields] for e in a['elements']],[[e.get(k) for k in fields] for e in b['elements']])

    def test_unsupported_surrounding_content_abstains(self):
        source=deepcopy(self.source)
        source['elements'].append(dict(id='unrelated',type='shape',shape_type='ellipse',fill_color='red',x=10,y=300,width=20,height=20))
        self.assertEqual([],list(series_candidates(source,dict(width=1080,height=1080),self.measurer)))

    def test_rotated_or_single_card_not_misclassified_as_series(self):
        source=deepcopy(self.source)
        source['elements'][3]['rotation']=10
        self.assertEqual([],list(series_candidates(source,dict(width=1080,height=1080),self.measurer)))


if __name__=='__main__':unittest.main()
