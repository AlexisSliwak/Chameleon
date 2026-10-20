import unittest
from engine.pixels import raster_diagnostics


class RasterSignalTests(unittest.TestCase):
    def test_contrast_uses_composited_backdrop_and_text_alpha(self):
        design = {'canvas': {'width': 120, 'height': 60}, 'elements': [
            dict(id='background',type='shape',x=0,y=0,width=120,height=60,
                 shape_type='rectangle',fill_color='rgba(0,0,0,1)',z_index=0),
            dict(id='copy',type='text',x=10,y=10,width=100,height=40,
                 content='Read',font_family='Solstice Sans',font_size=20,
                 color='rgba(255,255,255,1)',z_index=1)]}
        visible = raster_diagnostics(design)
        self.assertAlmostEqual(visible['mean_contrast_proxy'],21,places=3)
        self.assertEqual(visible['low_contrast_proxy'],0)
        design['elements'][1]['color']='rgba(255,255,255,0)'
        invisible = raster_diagnostics(design)
        self.assertAlmostEqual(invisible['mean_contrast_proxy'],1,places=3)
        self.assertGreater(invisible['low_contrast_proxy'],.7)

    def test_split_background_does_not_hide_invisible_text_in_average_gray(self):
        design={'canvas':{'width':200,'height':80},'elements':[
            dict(id='left',type='shape',shape_type='rectangle',x=0,y=0,width=100,height=80,
                 fill_color='rgba(0,0,0,1)',z_index=0),
            dict(id='right',type='shape',shape_type='rectangle',x=100,y=0,width=100,height=80,
                 fill_color='rgba(255,255,255,1)',z_index=0),
            dict(id='copy',type='text',x=0,y=0,width=200,height=80,content='MMMM MMMM',
                 font_family='Solstice Sans',font_size=30,color='rgba(0,0,0,1)',z_index=1)]}
        result=raster_diagnostics(design)
        # Exactly half the backdrop has 1:1 contrast; half has 21:1.
        self.assertAlmostEqual(result['sampled_low_contrast_proxy'],7/18,places=3)
        self.assertAlmostEqual(result['sampled_mean_contrast_proxy'],11,places=3)
        design['elements'][-1]['color']='rgba(255,255,255,1)'
        self.assertAlmostEqual(raster_diagnostics(design)['sampled_low_contrast_proxy'],7/18,places=3)

    def test_empty_and_outside_text_have_finite_zero_signal(self):
        d={'canvas':{'width':100,'height':100},'elements':[]}
        self.assertEqual(raster_diagnostics(d)['low_contrast_proxy'],0)
        d['elements']=[dict(id='outside',type='text',x=200,y=200,width=10,height=10,
                           content='A',font_family='Solstice Sans',font_size=8)]
        self.assertEqual(raster_diagnostics(d)['low_contrast_proxy'],0)

    def test_style_run_worst_color_and_input_preservation(self):
        from copy import deepcopy
        d={'canvas':{'width':80,'height':40},'elements':[
            dict(id='bg',type='shape',shape_type='rectangle',x=0,y=0,width=80,height=40,
                 fill_color='rgba(255,255,255,1)',z_index=0),
            dict(id='text',type='text',x=0,y=0,width=80,height=40,content='AB',font_family='Solstice Sans',
                 font_size=20,color='rgba(0,0,0,1)',z_index=1,
                 style_runs=[dict(start=0,end=1,color='rgba(255,255,255,1)')])]}
        before=deepcopy(d)
        self.assertAlmostEqual(raster_diagnostics(d)['sampled_low_contrast_proxy'],7/9,places=3)
        self.assertEqual(d,before)

    def test_element_opacity_matches_pinned_renderer_pixels(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from engine.main import render_to_png
        root=Path(__file__).resolve().parents[1]
        d={'canvas':{'width':200,'height':100},'elements':[
            dict(id='bg',type='shape',shape_type='rectangle',x=0,y=0,width=200,height=100,
                 fill_color='rgba(255,255,255,1)',z_index=0),
            dict(id='copy',type='text',x=10,y=10,width=180,height=60,content='Visible?',
                 font_family='Solstice Sans',font_size=24,color='rgba(0,0,0,1)',opacity=0,z_index=1)]}
        with TemporaryDirectory() as tmp:
            first=Path(tmp)/'zero.png';second=Path(tmp)/'one.png'
            render_to_png(d,root/'brand_kit/assets',first,root/'brand_kit/fonts')
            zero=raster_diagnostics(d)
            d['elements'][1]['opacity']=1
            render_to_png(d,root/'brand_kit/assets',second,root/'brand_kit/fonts')
            self.assertEqual(first.read_bytes(),second.read_bytes())
            self.assertEqual(zero,raster_diagnostics(d))
        # The pinned renderer's text fill resets the paint alpha to the span
        # color. Do not claim opacity behavior the official pixels do not have.
        self.assertAlmostEqual(zero['sampled_mean_contrast_proxy'],21)

    def test_identity_resize_preserves_design_but_exposes_raster_failure(self):
        from copy import deepcopy
        from engine.resize import resize_with_diagnostics
        d={'canvas':{'width':200,'height':100},'elements':[
            dict(id='bg',type='shape',shape_type='rectangle',x=0,y=0,width=200,height=100,
                 fill_color='rgba(255,255,255,1)',z_index=0),
            dict(id='copy',type='text',x=10,y=10,width=180,height=60,content='Invisible',
                 font_family='Solstice Sans',font_size=24,color='rgba(0,0,0,0)',opacity=1,z_index=1)]}
        original=deepcopy(d)
        output,diagnostics=resize_with_diagnostics(d,d['canvas'])
        self.assertEqual(output,original);self.assertEqual(d,original)
        self.assertEqual(diagnostics['method'],'identity')
        self.assertTrue(diagnostics['quality_warning'])
        self.assertGreater(diagnostics['raster']['sampled_low_contrast_proxy'],.7)
