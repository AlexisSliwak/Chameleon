"""Offline, counterfactual pixel review. Never used to select submission layouts.

Render differences measure an element's visible contribution, not recognizability
or aesthetic quality. Diagnostic recoloring/omission never changes saved designs.
"""
import argparse
from copy import deepcopy
import hashlib
from html import escape
from io import BytesIO
import json
import platform
from importlib.metadata import version
from pathlib import Path
import time

from PIL import Image, ImageChops
from engine.composition import composition_metrics
from engine.measure import TextMeasurer
from engine.pixels import luminance, raster_diagnostics
from engine.validation import validate_source, validate_output
from renderer.converter.convert import _get_renderer, convert_chameleon_to_crello

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = {
    'Readability': 'Read every line at native size: small copy, long tokens, clipping, missing glyphs and weak local contrast.',
    'Hierarchy and attention': 'Does the intended headline lead? Are secondary copy and actions distinct without overpowering the subject?',
    'Brand and imagery': 'Are logos and products recognizable, unobscured and proportionate? Inspect focal detail, cropping and transparent assets.',
    'Grouping and reading order': 'Do labels belong to their products? Is the sequence clear across columns, cards and split panels?',
    'Spacing and alignment': 'Check margins, padding, repeated gaps, baselines, crowded edges and accidental tangencies.',
    'Balance and source intent': 'Check visual weight, useful whitespace and intentional asymmetry against the source; symmetry is not automatically better.',
    'Layering and contrast': 'Check foreground occlusion, text on imagery, translucent layers and intentional backing shapes.',
    'Overall polish': 'Inspect awkward wraps, orphaned words, inconsistent peer treatment and whether the composition feels coherent at its intended size.',
}


def difference(a, b):
    channels = ImageChops.difference(a, b).split()
    return ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])


def energy(image):
    return sum(i*n for i, n in enumerate(image.histogram()))


def inspect_design(design, evidence=None, *, max_elements=64, max_size=1024,
                   fonts_dir=None, assets_dir=None):
    if not 1 <= max_elements <= 256 or not 64 <= max_size <= 2048:
        raise ValueError('max_elements must be 1..256 and max_size 64..2048')
    errors = validate_source(design)
    if errors:
        raise ValueError('; '.join(errors))
    fonts = Path(fonts_dir or ROOT/'brand_kit/fonts')
    assets = Path(assets_dir or ROOT/'brand_kit/assets')
    renderer = _get_renderer(str(fonts))
    warnings, renders = set(), 0
    def render(elements):
        nonlocal renders
        example, notes = convert_chameleon_to_crello(dict(design, elements=elements), renderer.font_manager, str(assets))
        warnings.update(notes)
        renders += 1
        return Image.open(BytesIO(renderer.render(example, max_size=max_size, format='png'))).convert('RGB')
    # Stable sort exactly matches the converter, including tied z-indices.
    ordered = sorted(design['elements'], key=lambda e: e.get('z_index', 0))
    full = render(ordered)
    if evidence:
        evidence.mkdir(parents=True, exist_ok=False)
        full.save(evidence/'full.png')
    eligible = [(i, e) for i, e in enumerate(ordered)
                if e['type']=='image' or (e['type']=='text' and e['content'].strip())]
    rows = []
    measurer = TextMeasurer(fonts)
    for number, (index, element) in enumerate(eligible[:max_elements]):
        under = render(ordered[:index])
        prefix = render(ordered[:index+1])
        without = render(ordered[:index]+ordered[index+1:])
        before, after = difference(prefix, under), difference(full, without)
        available, observed = energy(before), energy(after)
        row = dict(id=element['id'], type=element['type'],
                   contribution_retained=min(1., observed/available) if available else None,
                   unoccluded_contribution=available, final_contribution=observed,
                   flags=[])
        if not available:
            row['flags'].append('no measurable contribution before later layers; inspect camouflage, alpha or missing content')
        elif observed < available*.8:
            row['flags'].append('later layers reduce visible contribution; inspect intentional versus harmful occlusion')
        if element['type']=='text':
            extent = measurer.measure(element)
            row.update(font_size=element['font_size'], missing_glyphs=extent.missing_glyphs,
                       measured_lines=extent.lines, fits_box=extent.fits(element['width'],element['height']))
            if element['font_size'] < 8: row['flags'].append('tiny type: native-size human review required')
            if extent.missing_glyphs: row['flags'].append('unsupported glyphs')
            if not row['fits_box']: row['flags'].append('measured ink exceeds text box')
            masks = []
            for color in ('rgba(0,0,0,1)', 'rgba(255,255,255,1)'):
                recolored = deepcopy(element)
                recolored['color'] = color
                for run in recolored.get('style_runs', []):
                    if 'color' in run: run['color'] = color
                masks.append(render(ordered[:index]+[recolored]))
            mask = difference(*masks)
            # Strong-coverage glyph pixels reduce antialiasing bias. At tiny or
            # downsampled sizes there may be no core; report unknown, never pass.
            points = [i for i, alpha in enumerate(mask.tobytes()) if alpha >= 192]
            row['glyph_core_pixels'] = len(points)
            if points:
                final_pixels, beneath_pixels = full.load(), without.load()
                ratios = []
                for i in points:
                    point = (i % full.width, i // full.width)
                    a, b = luminance(final_pixels[point]), luminance(beneath_pixels[point])
                    ratios.append((max(a,b)+.05)/(min(a,b)+.05))
                row['low_contrast_glyph_fraction'] = sum(r < 4.5 for r in ratios)/len(ratios)
                row['median_glyph_contrast'] = sorted(ratios)[len(ratios)//2]
                if row['low_contrast_glyph_fraction'] > .1:
                    row['flags'].append('weak final-pixel glyph contrast; may include camouflage or occlusion')
            else:
                row['low_contrast_glyph_fraction'] = None
                row['median_glyph_contrast'] = None
                row['flags'].append('no reliable glyph core at review resolution; contrast unassessed')
        if evidence:
            filename = f'element-{number:03d}-contribution.png'
            after.save(evidence/filename)
            row['contribution_png'] = filename
        rows.append(row)
    return dict(elements=rows, omitted_ids=[e['id'] for _,e in eligible[max_elements:]],
                reviewed_count=len(rows), eligible_count=len(eligible), render_count=renders,
                raster_size=list(full.size), canvas=design['canvas'], warnings=sorted(warnings),
                limitations=['Diagnostic thresholds are engineering preferences, not official scores or WCAG certification.',
                             'Contribution loss is not semantic occlusion: identical overlapping pixels can hide identity without changing color.',
                             'Downsampling can hide thin strokes; no glyph core is unassessed, not a pass.',
                             'Image contribution does not establish subject, face, logo or crop quality.',
                             'No automatic aesthetic verdict; complete the human rubric at native size.'])


def create_report(task_path, output_path, directory, *, max_elements=64, max_size=1024):
    task, output = json.loads(task_path.read_text()), json.loads(output_path.read_text())
    source, target = task['source'], task['target_canvas']
    errors = validate_source(source)+validate_output(source, target, output)
    if errors: raise ValueError('; '.join(errors))
    directory.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        report = dict(version=1, purpose='diagnostic review; not selection or human ratings',
                      inputs={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (task_path, output_path)},
                      evaluator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      max_elements=max_elements, max_size=max_size, human_rubric=RUBRIC,
                      environment=dict(python=platform.python_version(), platform=platform.platform(), pillow=version('Pillow')),
                      runtime_files={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for folder in ('engine', 'renderer', 'brand_kit')
                                     for p in sorted((ROOT/folder).rglob('*'))
                                     if p.is_file() and '__pycache__' not in p.parts
                                     and (folder=='brand_kit' or p.suffix=='.py')})
        for label, design in (('source', source), ('output', output)):
            report[label] = inspect_design(design, directory/label, max_elements=max_elements, max_size=max_size)
        report['composition'] = composition_metrics(source, output, TextMeasurer())
        report['existing_raster'] = raster_diagnostics(output)
        report['elapsed_seconds'] = time.perf_counter()-started
        report['coverage_complete'] = not any(report[label]['omitted_ids'] for label in ('source', 'output'))
        (directory/'human-review.json').write_text(json.dumps(dict(status='unreviewed', dimensions={name: dict(rating='unreviewed', notes='') for name in RUBRIC}), indent=2)+chr(10))
        (directory/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
        # Freeze inputs for reproducibility; these are unchanged designs.
        (directory/'task.json').write_text(json.dumps(task, indent=2)+'\n')
        (directory/'output.json').write_text(json.dumps(output, indent=2)+'\n')
        parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Perceptual review</title>',
                 '<style>body{font:16px/1.5 system-ui;max-width:1400px;margin:auto;padding:24px;color:#17262b}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}img{max-width:100%}figure{margin:0}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #ccc;text-align:left;vertical-align:top}pre{white-space:pre-wrap} @media(max-width:700px){.pair{grid-template-columns:1fr}}</style>',
                 '<h1>Perceptual review</h1><p>Pixel evidence and human judgment are separate. These previews may be downsampled: inspect the original official PNG at native size before approving readability. No overall aesthetic score or human ratings are inferred.</p><p><a href="report.json">Full metrics, coverage and limitations</a> · <a href="human-review.json">Unfilled human review record</a></p><div class="pair">']
        for label in ('source','output'):
            data = report[label]
            parts.append(f'<figure><figcaption>{label.title()} · canvas {str(data["canvas"]["width"])+" × "+str(data["canvas"]["height"])} · raster {data["raster_size"]}</figcaption><a href="{label}/full.png"><img src="{label}/full.png" alt="{label} rendered preview"></a></figure>')
        parts.append('</div><h2>Human review checklist</h2><p>Record acceptable, needs work, unusable or unreviewed per dimension, with element IDs and a reason. Do not infer a pass from an empty warning list. Use the existing anonymous A/B workflow for comparative preference.</p><ul>')
        parts.extend(f'<li><strong>{escape(k)}:</strong> {escape(v)}</li>' for k,v in RUBRIC.items())
        parts.append('</ul><details><summary>Source-relative composition diagnostics</summary><p>These existing engineering proxies cover image prominence, hierarchy, grouping, alignment and reading order. They are not human ratings; zero loss is not proof of good design.</p><pre>'+escape(json.dumps(report['composition'],indent=2))+'</pre></details><p>Contribution images show the pixel change when an element is omitted: black means no visible change. This can indicate occlusion or camouflage; it is not a semantic subject mask.</p>')
        for label in ('source','output'):
            data=report[label]
            parts.append(f'<h2>{label.title()} pixel findings</h2><p>Reviewed {data["reviewed_count"]}/{data["eligible_count"]}; omitted IDs: {escape(str(data["omitted_ids"]))}</p><table><tr><th>Element</th><th>Contribution retained</th><th>Low-contrast glyph fraction</th><th>Findings</th></tr>')
            for row in data['elements']:
                retained = 'unassessed' if row['contribution_retained'] is None else format(row['contribution_retained'], '.1%')
                contrast = row.get('low_contrast_glyph_fraction')
                contrast = ('unassessed' if row['type']=='text' else 'not text') if contrast is None else format(contrast, '.1%')
                parts.append(f'<tr><td><a href="{label}/{row["contribution_png"]}">{escape(str(row["id"]))}</a> ({row["type"]})</td><td>{retained}</td><td>{contrast}</td><td>{escape("; ".join(row["flags"]) or "No automated flag; human review still required")}</td></tr>')
            parts.append('</table>')
        parts.append('<h2>Limitations</h2><ul>'+''.join('<li>'+escape(s)+'</li>' for s in report['output']['limitations'])+'</ul></html>')
        (directory/'index.html').write_text('\n'.join(parts))
        return report
    except Exception as error:
        (directory/'failure.json').write_text(json.dumps(dict(error=str(error),elapsed_seconds=time.perf_counter()-started),indent=2)+'\n')
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report-dir',type=Path,required=True)
    parser.add_argument('--max-elements',type=int,default=64)
    parser.add_argument('--max-size',type=int,default=1024)
    args=parser.parse_args()
    create_report(args.task,args.output,args.report_dir,max_elements=args.max_elements,max_size=args.max_size)
