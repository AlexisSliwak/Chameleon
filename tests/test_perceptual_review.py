from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.perceptual_review import inspect_design, create_report, RUBRIC


def fixture():
    return {'canvas':{'width':160,'height':80},'elements':[
        dict(id='background',type='shape',shape_type='rectangle',x=0,y=0,width=160,height=80,
             fill_color='rgba(255,255,255,1)',z_index=0),
        dict(id='copy',type='text',x=10,y=10,width=140,height=60,content='MMMM',
             font_family='Solstice Sans',font_size=28,color='rgba(0,0,0,1)',z_index=1)]}


def cover(x=0,width=160,alpha=1):
    return dict(id='cover',type='shape',shape_type='rectangle',x=x,y=0,width=width,height=80,
                fill_color=f'rgba(255,255,255,{alpha})',z_index=2)


class PerceptualReviewTests(unittest.TestCase):
    def row(self, design):
        return inspect_design(design)['elements'][0]

    def test_visible_text_and_input_preservation(self):
        design=fixture();before=deepcopy(design)
        row=self.row(design)
        self.assertEqual(design,before)
        self.assertEqual(row['contribution_retained'],1)
        self.assertGreater(row['glyph_core_pixels'],0)
        self.assertLess(row['low_contrast_glyph_fraction'],.05)

    def test_full_and_partial_occlusion(self):
        design=fixture();design['elements'].append(cover())
        hidden=self.row(design)
        self.assertEqual(hidden['contribution_retained'],0)
        self.assertEqual(hidden['low_contrast_glyph_fraction'],1)
        design['elements'][-1]=cover(width=48)
        partial=self.row(design)
        self.assertGreater(partial['contribution_retained'],.1)
        self.assertLess(partial['contribution_retained'],.9)
        self.assertGreater(partial['low_contrast_glyph_fraction'],.1)

    def test_translucent_occlusion_is_not_full_visibility(self):
        design=fixture();design['elements'].append(cover(alpha=.5))
        row=self.row(design)
        self.assertGreater(row['contribution_retained'],.4)
        self.assertLess(row['contribution_retained'],.6)

    def test_camouflage_and_color_alpha(self):
        for color in ('rgba(255,255,255,1)','rgba(0,0,0,0)'):
            with self.subTest(color=color):
                design=fixture();design['elements'][1]['color']=color
                row=self.row(design)
                self.assertIsNone(row['contribution_retained'])
                self.assertEqual(row['low_contrast_glyph_fraction'],1)

    def test_style_runs_and_rotation_follow_rendered_glyphs(self):
        design=fixture()
        design['elements'][1].update(rotation=8, style_runs=[dict(start=0,end=1,color='rgba(255,255,255,1)')])
        row=self.row(design)
        self.assertGreater(row['low_contrast_glyph_fraction'],.2)
        self.assertLess(row['low_contrast_glyph_fraction'],.8)

    def test_tied_layer_order_and_backing(self):
        design=fixture();back=cover();back['z_index']=1
        design['elements'].append(back)
        self.assertEqual(self.row(design)['contribution_retained'],0)
        design['elements']=[design['elements'][0],back,design['elements'][1]]
        self.assertEqual(self.row(design)['contribution_retained'],1)

    def test_budget_and_empty_coverage_are_explicit(self):
        design=fixture();other=deepcopy(design['elements'][1]);other['id']='other';design['elements'].append(other)
        report=inspect_design(design,max_elements=1)
        self.assertEqual(report['reviewed_count'],1)
        self.assertEqual(report['eligible_count'],2)
        self.assertEqual(report['omitted_ids'],['other'])
        self.assertEqual(report['render_count'],6)
        design['elements']=design['elements'][:1]
        self.assertEqual(inspect_design(design)['elements'],[])
        for kwargs in (dict(max_elements=0),dict(max_size=1)):
            with self.assertRaises(ValueError):inspect_design(design,**kwargs)

    def test_tiny_text_without_core_is_unassessed(self):
        design=fixture();design['elements'][1]['font_size']=1
        row=self.row(design)
        self.assertEqual(row['glyph_core_pixels'],0)
        self.assertIsNone(row['low_contrast_glyph_fraction'])
        self.assertTrue(any('unassessed' in flag for flag in row['flags']))

    def test_report_contract_links_escaping_and_no_overwrite(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);design=fixture();design['elements'][1]['id']='<copy>'
            task=root/'task.json';output=root/'output.json';directory=root/'report'
            task.write_text(json.dumps(dict(source=design,target_canvas=design['canvas'])))
            output.write_text(json.dumps(design))
            result=create_report(task,output,directory)
            self.assertEqual(result['human_rubric'],RUBRIC)
            self.assertTrue((directory/'source/full.png').is_file())
            self.assertTrue((directory/'output/element-000-contribution.png').is_file())
            page=(directory/'index.html').read_text()
            self.assertIn('&lt;copy&gt;',page);self.assertNotIn('<copy>',page)
            self.assertNotIn('human_ratings',result)
            with self.assertRaises(FileExistsError):create_report(task,output,directory)
            design['elements'][1]['content']='rewritten'
            output.write_text(json.dumps(design))
            with self.assertRaises(ValueError):create_report(task,output,root/'invalid')
            self.assertFalse((root/'invalid').exists())

    def test_image_occlusion_and_missing_asset_warning(self):
        from PIL import Image
        with TemporaryDirectory() as tmp:
            assets=Path(tmp);Image.new('RGBA',(30,30),(255,0,0,255)).save(assets/'subject.png')
            design=fixture();design['elements'][1]=dict(id='subject',type='image',x=10,y=10,width=30,height=30,asset_id='subject.png',fit='contain',z_index=1)
            visible=inspect_design(design,assets_dir=assets)['elements'][0]
            self.assertEqual(visible['contribution_retained'],1)
            design['elements'].append(cover())
            self.assertEqual(inspect_design(design,assets_dir=assets)['elements'][0]['contribution_retained'],0)
            design['elements'][1]['asset_id']='absent.png'
            self.assertTrue(inspect_design(design,assets_dir=assets)['warnings'])

    def test_empty_box_background_does_not_count_as_glyph_contrast(self):
        from engine.pixels import raster_diagnostics
        design=fixture();design['elements'][1]['content']='Hi'
        patch=cover(x=80,width=80);patch['z_index']=0
        patch['fill_color']='rgba(0,0,0,1)'
        design['elements'].insert(1,patch)
        self.assertGreater(raster_diagnostics(design)['sampled_low_contrast_proxy'],.1)
        self.assertLess(self.row(design)['low_contrast_glyph_fraction'],.05)

    def test_failure_is_retained_without_success_report(self):
        from unittest.mock import patch
        with TemporaryDirectory() as tmp:
            root=Path(tmp);design=fixture();task=root/'task.json';output=root/'output.json'
            task.write_text(json.dumps(dict(source=design,target_canvas=design['canvas'])))
            output.write_text(json.dumps(design))
            with patch('scripts.perceptual_review._get_renderer',side_effect=RuntimeError('renderer unavailable')):
                with self.assertRaises(RuntimeError):create_report(task,output,root/'failed')
            self.assertIn('renderer unavailable',(root/'failed/failure.json').read_text())
            self.assertFalse((root/'failed/report.json').exists())
