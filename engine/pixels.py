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
    contrasts,penalties,legacy_contrasts,busyness = [],[],[],[]
    for e in design['elements']:
        if e['type']!='text' or not e['content'].strip():continue
        box=(max(0,floor(e['x']*sx)),max(0,floor(e['y']*sy)),
             min(raster.width,ceil((e['x']+e['width'])*sx)),min(raster.height,ceil((e['y']+e['height'])*sy)))
        if box[2]<=box[0] or box[3]<=box[1]:continue
        stat = ImageStat.Stat(raster.crop(box))
        colors = [e.get('color','rgba(0,0,0,1)')] + [r['color'] for r in e.get('style_runs',[]) if 'color' in r]
        # Do not average colors before computing contrast: black-on-black can
        # disappear on half an image even if the average gray appears safe.
        # Nearest sampling preserves observed colors, with a fixed work budget.
        crop=raster.crop(box)
        samples=crop.resize((min(32,crop.width),min(32,crop.height)),Image.Resampling.NEAREST)
        counts=samples.getcolors(maxcolors=1024)
        local=[]
        legacy=[]
        average_bg=luminance(stat.mean[:3])
        for color in colors:
            rgba=parse_rgba(color)
            average_fg=luminance([rgba[k]*rgba[3]+stat.mean[k]*(1-rgba[3]) for k in range(3)])
            legacy.append((max(average_fg,average_bg)+.05)/(min(average_fg,average_bg)+.05))
            ratios=[]
            for count,rgb in counts:
                bg=luminance(rgb)
                fg=luminance([rgba[k]*rgba[3]+rgb[k]*(1-rgba[3]) for k in range(3)])
                ratio=(max(fg,bg)+.05)/(min(fg,bg)+.05)
                ratios.append((count,ratio))
            area=samples.width*samples.height
            local.append((sum(n*c for n,c in ratios)/area,
                          sum(n*max(0,1-c/4.5) for n,c in ratios)/area))
        legacy_contrasts.append(min(legacy))
        contrasts.append(min(c for c,p in local))
        penalties.append(max(p for c,p in local))
        busyness.append(sum(stat.stddev[:3])/(3*255))
    penalty=sum(penalties)/max(1,len(penalties))
    return {'mean_contrast_proxy':sum(legacy_contrasts)/max(1,len(legacy_contrasts)),
            'low_contrast_proxy':sum(max(0,1-c/4.5) for c in legacy_contrasts)/max(1,len(legacy_contrasts)),
            'sampled_mean_contrast_proxy':sum(contrasts)/max(1,len(contrasts)),
            'sampled_low_contrast_proxy':penalty,'busyness_proxy':sum(busyness)/max(1,len(busyness)),
            'warnings':warnings}
