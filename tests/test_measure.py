"""Compare measured extents with pixels from the independent official PNG path."""
import copy
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from engine.measure import TextMeasurer
from renderer.converter.convert import render_design_to_png

ROOT = Path(__file__).resolve().parents[1]


class MeasurementTests(unittest.TestCase):
    def test_batch_renderer_keeps_native_canvas_above_2048(self):
        from engine.main import render_to_png
        design = dict(canvas=dict(width=2050,height=40),elements=[
            dict(id='shape',type='shape',x=0,y=0,width=2050,height=40,
                 shape_type='rectangle',fill_color='rgba(20,40,60,1)')])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'wide.png'
            render_to_png(design,ROOT/'brand_kit/assets',output,ROOT/'brand_kit/fonts')
            with Image.open(output) as image:
                self.assertEqual((2050,40),image.size)

    def test_measurement_encloses_official_rendered_ink(self):
        measurer = TextMeasurer(ROOT/'brand_kit/fonts')
        base = dict(id='text',type='text',x=80.,y=50.,width=240.,height=160.,
                    font_size=25.,content='Actual mixed Text wraps here',
                    font_family='Solstice Sans',color='rgba(0,0,0,1)',z_index=1)
        variants = [{}, {'font_style':'italic','capitalize':True,'letter_spacing':1.2},
                    {'style_runs':[dict(start=7,end=16,font_weight='bold')], 'width':130.},
                    {'content':'UnbreakableTokenHere','width':60.},
                    {'content':'Two\nlines','text_align':'center','line_height':1.4}]
        with tempfile.TemporaryDirectory() as directory:
            for i, fields in enumerate(variants):
                with self.subTest(fields=fields):
                    element = dict(base, **fields)
                    before = copy.deepcopy(element)
                    extent = measurer.measure(element)
                    design = dict(canvas=dict(width=700,height=400),elements=[
                        dict(id='bg',type='shape',x=0,y=0,width=700,height=400,
                             shape_type='rectangle',fill_color='rgba(255,255,255,1)',z_index=0),element])
                    path = Path(directory)/f'case-{i}.png'
                    render_design_to_png(design,ROOT/'brand_kit/assets',path,
                                         fonts_dir=ROOT/'brand_kit/fonts',max_size=700)
                    image = Image.open(path).convert('RGBA')
                    self.assertEqual((700,400),image.size)
                    pixels = image.load()
                    ink = [(x,y) for y in range(image.height) for x in range(image.width)
                           if pixels[x,y][3] > 128 and max(pixels[x,y][:3]) < 128]
                    self.assertTrue(ink)
                    bounds = (min(x for x,y in ink)-element['x'],
                              min(y for x,y in ink)-element['y'],
                              max(x for x,y in ink)+1-element['x'],
                              max(y for x,y in ink)+1-element['y'])
                    for measured, raster in zip((extent.left,extent.top,extent.right,extent.bottom),bounds):
                        self.assertAlmostEqual(measured,raster,delta=2.0)
                    self.assertEqual(before,element)


if __name__ == '__main__':
    unittest.main()
