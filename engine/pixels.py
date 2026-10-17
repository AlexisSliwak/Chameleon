"""Bounded raster diagnostics using the unchanged official converter.

Local contrast/busyness are engineering signals, not subject recognition or an
aesthetic judge. All asset pixels remain unchanged. No network or model loads.
"""
from io import BytesIO
from math import floor, ceil
from pathlib import Path

from PIL import Image, ImageStat
from renderer.converter.convert import _get_renderer, convert_chameleon_to_crello
from renderer.converter.colorutil import parse_rgba


def luminance(rgb):
    values = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in (c/255 for c in rgb)]
    return .2126*values[0]+.7152*values[1]+.0722*values[2]


def raster_diagnostics(design, fonts_dir=None, assets_dir=None):
    root = Path(__file__).resolve().parents[1]
    assets = Path(assets_dir or root/'brand_kit/assets')
    fonts = Path(fonts_dir or root/'brand_kit/fonts')
    renderer = _get_renderer(str(fonts))
    backdrop = dict(design, elements=[e for e in design['elements'] if e['type']!='text'])
    example,warnings = convert_chameleon_to_crello(backdrop,renderer.font_manager,str(assets))
    raster = Image.open(BytesIO(renderer.render(example,max_size=512,format='png'))).convert('RGB')
    sx,sy = raster.width/design['canvas']['width'],raster.height/design['canvas']['height']
    contrasts,busyness = [],[]
    for e in design['elements']:
        if e['type']!='text' or not e['content'].strip():continue
        box=(max(0,floor(e['x']*sx)),max(0,floor(e['y']*sy)),
             min(raster.width,ceil((e['x']+e['width'])*sx)),min(raster.height,ceil((e['y']+e['height'])*sy)))
        if box[2]<=box[0] or box[3]<=box[1]:continue
        stat = ImageStat.Stat(raster.crop(box))
        bg = luminance(stat.mean[:3])
        colors = [e.get('color','rgba(0,0,0,1)')] + [r['color'] for r in e.get('style_runs',[]) if 'color' in r]
        local=[]
        for color in colors:
            rgba=parse_rgba(color)
            fg=luminance([rgba[k]*rgba[3]+stat.mean[k]*(1-rgba[3]) for k in range(3)])
            local.append((max(fg,bg)+.05)/(min(fg,bg)+.05))
        contrasts.append(min(local))
        busyness.append(sum(stat.stddev[:3])/(3*255))
    penalty=sum(max(0,1-c/4.5) for c in contrasts)/max(1,len(contrasts))
    return {'mean_contrast_proxy':sum(contrasts)/max(1,len(contrasts)),
            'low_contrast_proxy':penalty,'busyness_proxy':sum(busyness)/max(1,len(busyness)),
            'warnings':warnings}
