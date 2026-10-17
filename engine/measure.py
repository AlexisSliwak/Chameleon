"""Text extents from the official converter and renderer's actual glyph path.

The converter wraps before applying style runs/capitalization. Preserve that
behavior, including its inclusive style endpoints, rather than estimating with
a different typography engine. Pixel evaluation remains a separate check.
"""
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path

import skia
from cr_renderer.schema import TextElement
from cr_renderer.text_utils import generate_map, make_text_spans, make_text_blob, get_textalign_offset
from renderer.converter.brand_fonts import load_brand_font_manager
from renderer.converter.convert import _append_text


@dataclass(frozen=True)
class TextExtent:
    left: float
    top: float
    right: float
    bottom: float
    lines: int
    missing_glyphs: int

    def fits(self, width, height, tolerance=0.75):
        return (self.left >= -tolerance and self.top >= -tolerance
                and self.right <= width + tolerance and self.bottom <= height + tolerance)


class TextMeasurer:
    def __init__(self, fonts_dir=None):
        self.fonts_dir = Path(fonts_dir or Path(__file__).resolve().parents[1] / 'brand_kit/fonts')
        self.font_manager = load_brand_font_manager(str(self.fonts_dir))
        self.cache = {}

    def measure(self, element):
        keys = ('content', 'font_family', 'font_size', 'font_weight', 'font_style',
                'italic', 'color', 'width', 'line_height', 'letter_spacing',
                'capitalize', 'style_runs', 'text_align')
        key = json.dumps({k: element[k] for k in keys if k in element}, sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        data = defaultdict(list)
        _append_text(data, element, self.font_manager)
        text = TextElement(
            uuid='', type='textElement', width=max(0.001, element['width']), height=1,
            text=data['text'][0], fontSize=data['font_size'][0], font=data['font'][0],
            lineHeight=data['line_height'][0], textAlign=data['text_align'][0],
            capitalize=data['capitalize'][0], letterSpacing=data['letter_spacing'][0],
            boldMap=generate_map(data['font_bold'][0]),
            italicMap=generate_map(data['font_italic'][0]),
            colorMap=generate_map(data['text_color'][0]), lineMap=generate_map(data['text_line'][0]))
        bounds = []
        missing = 0
        lines = list(make_text_spans(text))
        for row, spans in enumerate(lines):
            blobs = [make_text_blob(text, span, self.font_manager) for span in spans]
            x = get_textalign_offset(text.textAlign, text.width, blobs)
            for span, blob in zip(spans, blobs):
                weight = 'bold' if span.style.bold else 'regular'
                style = ('bolditalic' if span.style.bold else 'italic') if span.style.italic else weight
                font = skia.Font(skia.Typeface.MakeFromData(
                    self.font_manager.lookup(text.font, weight, style)), int(text.fontSize))
                chars = (span.text.upper() if text.capitalize else span.text).strip('\n')
                glyphs = font.textToGlyphs(chars)
                missing += sum(g == 0 for g, c in zip(glyphs, chars) if not c.isspace())
                y = row * text.fontSize * (text.lineHeight or 1) - blob.metrics.fAscent
                for j, (pos, box) in enumerate(zip(font.getXPos(glyphs), font.getBounds(glyphs))):
                    if not box.isEmpty():
                        dx = x + pos + text.letterSpacing * j
                        bounds.append((dx + box.left(), y + box.top(), dx + box.right(), y + box.bottom()))
                x += blob.width
        result = TextExtent(min((b[0] for b in bounds), default=0), min((b[1] for b in bounds), default=0),
                            max((b[2] for b in bounds), default=0), max((b[3] for b in bounds), default=0),
                            len(lines), missing)
        self.cache[key] = result
        return result

    def fit(self, element, width, height, preferred):
        """Largest feasible sampled integer renderer size; no monotonic wrap assumption."""
        upper = max(1, int(preferred))
        # Exact scan near the upper bound, then coarse stepping plus local refinement.
        sizes = sorted(set([1, upper] + list(range(max(1, upper-8), upper))
                           + [max(1, int(upper * k / 48)) for k in range(1, 49)]), reverse=True)
        for size in sizes:
            trial = dict(element, width=width, height=height, font_size=float(size))
            extent = self.measure(trial)
            if extent.fits(width, height) and not extent.missing_glyphs:
                return trial, extent
        trial = dict(element, width=width, height=height, font_size=1.0)
        return trial, self.measure(trial)
