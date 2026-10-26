"""Development-only rendered comparison; never an official score or holdout result.

Run with the live runtime dependencies installed. --output-dir must not exist.
Runs the production engine only; retains failed cases and prior-run comparisons.
"""
import argparse
import ast
import copy
import hashlib
import html
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('full',)  # Stable result key for comparisons with historical runs.


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def targets(task):
    proposed = [('provided', task['target_canvas']), ('identity', task['source']['canvas']),
                ('square', {'width': 512, 'height': 512}),
                ('portrait', {'width': 600, 'height': 900}),
                ('banner', {'width': 728, 'height': 90})]
    result = []
    for label, canvas in proposed:
        existing = next((item for item in result if item['canvas'] == canvas), None)
        if existing:
            existing['labels'].append(label)
        else:
            result.append({'labels': [label], 'canvas': copy.deepcopy(canvas)})
    return result




def file_hashes(directory):
    return {p.relative_to(directory).as_posix(): digest(p)
            for p in sorted(directory.rglob('*')) if p.is_file()}


def gallery(directory, manifest, rows, previews):
    esc = lambda value: html.escape(str(value), quote=True)
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>Chameleon development comparison</title>',
             '<style>body{font:16px system-ui;margin:24px;background:#eee;color:#222} '
             '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px} '
             'article{background:white;padding:12px;min-width:0}img{max-width:100%;height:auto;'
             'background:#ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}'
             '.bad{color:#a00}section{margin:28px 0}a{color:#174ea6}'
             '@media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(200px,1fr))}}'
             '</style><h1>Development comparison</h1>',
             '<p>Public samples only; shared brand kit; not held out. Metrics are engine proxies, '
             'not Adobe scores or independent preference judgments. Invalid outputs and failures '
             'remain in this report. No automatic superiority claim is made.</p>',
             '<p>Thumbnails fit their columns and can disguise small text. Open each PNG to inspect '
             'its native pixels. Source previews have different dimensions; inspect each output at its target size.</p>',
             '<p><a href="manifest.json">Frozen manifest</a> · <a href="results.json">All results</a></p>']
    for fixture in manifest['fixtures']:
        source_name = fixture['name']
        parts.append(f'<h2>{esc(source_name)}</h2>')
        preview = previews.get(source_name, {})
        if preview.get('png'):
            parts.append(f'<a href="{esc(preview["png"])}"><img style="max-height:280px;max-width:400px" '
                         f'src="{esc(preview["png"])}" alt="Source design"></a>')
        if preview.get('error'):
            parts.append(f'<p class="bad">Source render failed: {esc(preview["error"])}</p>')
        for item in fixture['targets']:
            canvas = item['canvas']
            parts.append(f'<section><h3>{esc(" / ".join(item["labels"]))}: '
                         f'{canvas["width"]} × {canvas["height"]}</h3><div class="grid">')
            for method in METHODS:
                row = next(r for r in rows if r['fixture'] == source_name and
                           r['target'] == canvas and r['method'] == method)
                parts.append(f'<article><h4>Chameleon output</h4>')
                if row.get('png'):
                    parts.append(f'<a href="{esc(row["png"])}"><img src="{esc(row["png"])}" '
                                 f'alt="{esc(method)} at {canvas["width"]} by {canvas["height"]}"></a>')
                if row.get('json'):
                    parts.append(f'<p><a href="{esc(row["json"])}">Output JSON</a></p>')
                details = {k: v for k, v in row.items() if k not in ('fixture', 'target', 'method', 'json', 'png')}
                parts.append(f'<pre>{esc(json.dumps(details, indent=2, ensure_ascii=False))}</pre></article>')
            parts.append('</div></section>')
    parts.append('</html>')
    (directory / 'index.html').write_text('\n'.join(parts), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'input')
    parser.add_argument('--assets-dir', type=Path, default=ROOT / 'brand_kit/assets')
    parser.add_argument('--fonts-dir', type=Path, default=None)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if output.exists():
        parser.error('--output-dir must not exist; previous runs are never overwritten')
    assets = args.assets_dir.resolve()
    fonts = args.fonts_dir.resolve() if args.fonts_dir else assets.parent / 'fonts'
    paths = sorted(args.input_dir.glob('chameleon_sample_level*.json'))
    if len(paths) != 3:
        parser.error('expected exactly the three public chameleon_sample_level*.json fixtures')
    tasks = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in paths}
    resize_source = (ROOT / 'engine/resize.py').read_text(encoding='utf-8')
    assess_node = next(n for n in ast.parse(resize_source).body if isinstance(n, ast.FunctionDef) and n.name == 'assess')
    manifest = {
        'created_utc': datetime.now(timezone.utc).isoformat(), 'split': 'public-development-NOT-holdout',
        'methods': list(METHODS), 'fixtures': [
            {'name': p.name, 'sha256': digest(p), 'targets': targets(tasks[p.name])} for p in paths],
        'selection_and_metric_weights': {
            'authority': 'Frozen engine_snapshot contains selection, composition and pixel coefficients; not official scoring. assess below is the legacy diagnostic only.',
            'source': ast.get_source_segment(resize_source, assess_node),
            'caution': 'Selection combines composition, safety and pixel terms. No engine proxy is independent evidence of visual superiority.'},
        'case_weighting': 'No pooled quality ranking. Each unique fixture-target-method appears once.',
        'validity_profile': 'Independent validate_output: conservation, strict bounds/style policy and ordinary-image aspect.',
        'renderer': 'official converter; no fallback; source and all method outputs rendered where possible',
        'execution': 'one production engine per case; timings are descriptive, not controlled cold-start speed comparisons',
        'python': sys.version, 'platform': platform.platform(),
        'code_sha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted((ROOT / 'engine').glob('*.py'))},
        'evaluator_sha256': digest(Path(__file__)),
        'asset_sha256': file_hashes(assets), 'font_sha256': file_hashes(fonts),
        'asset_directory': str(assets), 'font_directory': str(fonts),
    }
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'engine_snapshot'
    snapshot.mkdir()
    for path in sorted((ROOT / 'engine').glob('*.py')):
        (snapshot / path.name).write_bytes(path.read_bytes())
    (output / 'evaluator.py').write_bytes(Path(__file__).read_bytes())
    write_json(output / 'manifest.json', manifest)  # Freeze before imports or measured work.
    rows, previews, environment = [], {}, {}
    runtime_error = None
    sys.path.insert(0, str(ROOT))
    try:
        from engine.resize import background_indices, assess, resize_with_diagnostics
        from engine.measure import TextMeasurer
        from engine.validation import validate_output
        from engine.main import render_to_png
        for package in ('Pillow', 'cr-renderer', 'skia-python'):
            try:
                environment[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                environment[package] = 'metadata unavailable'
    except Exception as exc:
        runtime_error = f'{type(exc).__name__}: {exc}'
        environment['runtime_import_error'] = runtime_error
    write_json(output / 'environment.json', environment)
    for index, fixture in enumerate(manifest['fixtures']):
        name = fixture['name']
        task = tasks[name]
        source = task['source']
        folder = output / f'source-{index + 1}'
        folder.mkdir()
        try:
            if runtime_error:
                raise RuntimeError(runtime_error)
            preview_path = folder / 'source.png'
            warnings = render_to_png(source, assets, preview_path, fonts)
            previews[name] = {'png': preview_path.relative_to(output).as_posix(), 'warnings': warnings}
        except Exception as exc:
            previews[name] = {'error': f'{type(exc).__name__}: {exc}'}
        for target_index, item in enumerate(fixture['targets']):
            target = item['canvas']
            for method in METHODS:
                source = copy.deepcopy(task['source'])
                target = copy.deepcopy(item['canvas'])
                case = folder / f'target-{target_index + 1}-{method}'
                case.mkdir()
                row = {'fixture': name, 'target': target, 'method': method, 'status': 'failed',
                       'valid': None, 'validation_errors': [], 'warnings': [], 'timings_seconds': {}}
                started = time.perf_counter()
                try:
                    if runtime_error:
                        raise RuntimeError(runtime_error)
                    original = copy.deepcopy(source)
                    original_target = copy.deepcopy(target)
                    backgrounds = background_indices(source)
                    measurer = TextMeasurer(fonts)
                    begin = time.perf_counter()
                    design, row['engine_diagnostics'] = resize_with_diagnostics(
                        source, target, fonts_dir=fonts, assets_dir=assets)
                    row['timings_seconds']['generate'] = time.perf_counter() - begin
                    if source != original or target != original_target:
                        source, target = original, original_target
                        raise ValueError('engine mutated source/target')
                    write_json(case / 'output.json', design)
                    row['json'] = (case / 'output.json').relative_to(output).as_posix()
                    row['validation_errors'] = validate_output(original, original_target, design)
                    row['valid'] = not row['validation_errors']
                    # Assessment failure must not hide an otherwise renderable output.
                    begin = time.perf_counter()
                    try:
                        row['metrics'] = assess(original, design, backgrounds, measurer, assets)
                    except Exception as exc:
                        row['assessment_error'] = f'{type(exc).__name__}: {exc}'
                    row['timings_seconds']['assess'] = time.perf_counter() - begin
                    begin = time.perf_counter()
                    row['warnings'] = render_to_png(design, assets, case / 'output.png', fonts)
                    row['timings_seconds']['render'] = time.perf_counter() - begin
                    row['png'] = (case / 'output.png').relative_to(output).as_posix()
                    row['status'] = 'rendered-valid' if row['valid'] else 'rendered-invalid'
                except Exception as exc:
                    row['error'] = f'{type(exc).__name__}: {exc}'
                row['timings_seconds']['total'] = time.perf_counter() - started
                rows.append(row)
                write_json(case / 'result.json', row)
                # Incremental evidence survives an interrupted later case.
                write_json(output / 'results.json', {'source_previews': previews, 'cases': rows})
                print(json.dumps({'fixture': name, 'target': target, 'method': method, 'status': row['status']}), flush=True)
    gallery(output, manifest, rows, previews)
    summary = {'split': manifest['split'], 'unique_sources': len(manifest['fixtures']),
               'unique_source_target_pairs': sum(len(f['targets']) for f in manifest['fixtures']),
               'methods': {method: {'cases': sum(r['method'] == method for r in rows),
                                   'valid_contract': sum(r['method'] == method and r['valid'] is True for r in rows),
                                   'invalid_contract': sum(r['method'] == method and r['valid'] is False for r in rows),
                                   'rendered': sum(r['method'] == method and 'png' in r for r in rows),
                                   'failed': sum(r['method'] == method and r['status'] == 'failed' for r in rows)}
                           for method in METHODS},
               'source_render_failures': sum('error' in p for p in previews.values()),
               'gallery': str(output / 'index.html'),
               'interpretation': 'Development diagnostics only. No automatic quality superiority or official score claim.'}
    summary['code_unchanged_during_run'] = all(
        (ROOT/path).is_file() and digest(ROOT/path)==expected
        for path,expected in manifest['code_sha256'].items())
    write_json(output / 'summary.json', summary)
    print(json.dumps(summary, indent=2))
    return 1 if (any(r['status'] != 'rendered-valid' for r in rows)
                 or summary['source_render_failures']
                 or not summary['code_unchanged_during_run']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
