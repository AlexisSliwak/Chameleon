"""Synthetic development challenges; never an independent human-quality holdout.

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
import os
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('full',)  # One production engine; historical result key retained.


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')






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
             '<p>Agent-authored synthetic designs; shared brand kit; not independent holdouts. Metrics are engine proxies, '
             'not Adobe scores or independent preference judgments. Invalid outputs and failures '
             'remain in this report. No automatic superiority claim is made.</p>',
             '<p>Thumbnails fit their columns and can disguise small text. Open each PNG to inspect '
             'its native pixels. Source previews have different dimensions; inspect each output at its target size.</p>',
             '<p><a href="manifest.json">Frozen manifest</a> · <a href="results.json">All results</a></p>']
    baseline = Path(manifest['baseline_directory']) if manifest.get('baseline_directory') else None
    baseline_rows = json.loads((baseline / 'results.json').read_text())['cases'] if baseline else []
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
                row = next((r for r in rows if r['fixture'] == source_name and
                           r['target'] == canvas and r['method'] == method), None)
                if row is None:
                    continue
                parts.append(f'<article><h4>Chameleon output</h4>')
                if row.get('png'):
                    parts.append(f'<a href="{esc(row["png"])}"><img src="{esc(row["png"])}" '
                                 f'alt="{esc(method)} at {canvas["width"]} by {canvas["height"]}"></a>')
                if row.get('json'):
                    parts.append(f'<p><a href="{esc(row["json"])}">Output JSON</a></p>')
                details = {k: v for k, v in row.items() if k not in ('fixture', 'target', 'method', 'json', 'png')}
                parts.append(f'<pre>{esc(json.dumps(details, indent=2, ensure_ascii=False))}</pre></article>')
            parts.append('</div></section>')
    if baseline:
        parts.append('<h2>Same-case full-engine comparison with prior run</h2>')
        for row in rows:
            if row['method'] != 'full':
                continue
            old = next((r for r in baseline_rows if r['fixture'] == row['fixture'] and r['target'] == row['target'] and r['method'] == 'full'), None)
            parts.append('<h3>' + esc(row['fixture']) + ' / ' + esc(row['target']) + '</h3><div class="grid">')
            for label, item, base in [('Prior run', old, baseline), ('Current run', row, directory)]:
                parts.append('<article><h4>' + label + '</h4>')
                if item and item.get('png'):
                    href = Path(os.path.relpath(base / item['png'], directory)).as_posix()
                    parts.append('<a href="' + esc(href) + '"><img src="' + esc(href) + '" alt="' + label + '"></a>')
                else:
                    parts.append('<p>Missing or failed render</p>')
                parts.append('</article>')
            parts.append('</div>')
    parts.append('</html>')
    (directory / 'index.html').write_text('\n'.join(parts), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'tests/fixtures/design-families')
    parser.add_argument('--assets-dir', type=Path, default=ROOT / 'brand_kit/assets')
    parser.add_argument('--fonts-dir', type=Path, default=None)
    parser.add_argument('--baseline-dir', type=Path, help='Existing local challenge run for side-by-side gallery')
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if output.exists():
        parser.error('--output-dir must not exist; previous runs are never overwritten')
    assets = args.assets_dir.resolve()
    fonts = args.fonts_dir.resolve() if args.fonts_dir else assets.parent / 'fonts'
    matrix_path = args.input_dir / 'challenge-matrix.json'
    matrix = json.loads(matrix_path.read_text(encoding='utf-8'))
    paths = []
    matrix_targets = {}
    for family in matrix['families']:
        path = (args.input_dir / family['file']).resolve()
        if path.parent != args.input_dir.resolve() or path in paths:
            parser.error('matrix fixture paths must be unique files directly in input directory')
        paths.append(path)
        canvases = family['targets']
        if not canvases or any(set(c) != {'width', 'height'} or any(type(v) is not int or v <= 0 for v in c.values()) for c in canvases):
            parser.error('matrix targets must have positive integer width and height')
        if len({(c['width'], c['height']) for c in canvases}) != len(canvases):
            parser.error('duplicate matrix target')
        matrix_targets[path.name] = [{'labels': ['identity' if i == 0 else 'challenge-' + str(i)], 'canvas': c} for i, c in enumerate(canvases)]
    tasks = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in paths}
    baseline = args.baseline_dir.resolve() if args.baseline_dir else None
    if baseline and not (baseline / 'results.json').is_file():
        parser.error('baseline directory must contain results.json')
    if baseline:
        prior = json.loads((baseline / 'manifest.json').read_text(encoding='utf-8'))
        expected = {p.name: digest(p) for p in paths}
        actual = {f['name']: f['sha256'] for f in prior['fixtures']}
        if expected != actual or prior.get('challenge_matrix_sha256') != digest(matrix_path):
            parser.error('baseline fixture or target-matrix hashes differ; comparison requires identical inputs')
    resize_source = (ROOT / 'engine/resize.py').read_text(encoding='utf-8')
    assess_node = next(n for n in ast.parse(resize_source).body if isinstance(n, ast.FunctionDef) and n.name == 'assess')
    manifest = {
        'created_utc': datetime.now(timezone.utc).isoformat(), 'split': 'agent-authored-synthetic-development-NOT-independent-holdout',
        'methods': list(METHODS), 'fixtures': [
            {'name': p.name, 'sha256': digest(p), 'targets': matrix_targets[p.name]} for p in paths],
        'selection_and_metric_weights': {
            'authority': 'Engine hashes identify the production implementation; assess below is a legacy diagnostic, not the selection objective.',
            'source': ast.get_source_segment(resize_source, assess_node),
            'caution': 'Selection combines composition, safety and pixel terms. Engine proxies are not independent evidence of visual superiority.'},
        'case_weighting': 'No pooled quality ranking. Each unique fixture-target-method appears once.',
        'validity_profile': 'Independent validate_output: conservation, strict bounds/style policy and ordinary-image aspect.',
        'renderer': 'official converter; no fallback; source and all method outputs rendered where possible',
        'execution': 'one production engine per case; timings are descriptive, not controlled cold-start speed comparisons',
        'python': sys.version, 'platform': platform.platform(),
        'code_sha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted((ROOT / 'engine').glob('*.py'))},
        'evaluator_sha256': digest(Path(__file__)),
        'challenge_matrix_sha256': digest(matrix_path),
        'baseline_directory': str(baseline) if baseline else None,
        'baseline_results_sha256': digest(baseline / 'results.json') if baseline else None,
        'asset_sha256': file_hashes(assets), 'font_sha256': file_hashes(fonts),
        'asset_directory': str(assets), 'font_directory': str(fonts),
    }
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'manifest.json', manifest)  # Freeze before imports or measured work.
    (output / 'evaluator.py').write_bytes(Path(__file__).read_bytes())
    frozen = output / 'inputs'
    frozen.mkdir()
    for path in paths + [matrix_path]:
        (frozen / path.name).write_bytes(path.read_bytes())
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
                gallery(output, manifest, rows, previews)
                print(json.dumps({'fixture': name, 'target': target, 'method': method, 'status': row['status']}), flush=True)
    gallery(output, manifest, rows, previews)
    summary = {'split': manifest['split'], 'unique_sources': len(manifest['fixtures']),
               'unique_source_target_pairs': sum(len(f['targets']) for f in manifest['fixtures']),
               'methods': {method: {'cases': sum(r['method'] == method for r in rows),
                                   'valid_contract': sum(r['method'] == method and r['valid'] is True for r in rows),
                                   'rendered': sum(r['method'] == method and 'png' in r for r in rows),
                                   'failed': sum(r['method'] == method and r['status'] == 'failed' for r in rows)}
                           for method in METHODS},
               'source_render_failures': sum('error' in p for p in previews.values()),
               'gallery': str(output / 'index.html'),
               'interpretation': 'Development diagnostics only. No automatic quality superiority or official score claim.'}
    write_json(output / 'summary.json', summary)
    print(json.dumps(summary, indent=2))
    return 1 if any(r['status'] == 'failed' for r in rows) or any('error' in p for p in previews.values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
