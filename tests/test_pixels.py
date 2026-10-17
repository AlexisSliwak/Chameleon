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
