"""Offline batch runner: validate, render for real, then publish each output pair.

Per-task failures remove stale outputs for that task and do not stop later tasks.
Pair publication rolls back on ordinary exceptions; two filesystem names cannot
be atomically replaced together across process termination. Reruns clean stale pairs.
"""
import argparse
import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from engine.validation import validate_source, validate_target, validate_output


def resize_with_diagnostics(source, target, fonts_dir=None, assets_dir=None):
    from engine.resize import resize_with_diagnostics as implementation
    return implementation(source, target, fonts_dir=fonts_dir, assets_dir=assets_dir)


def render_to_png(design, assets_dir, png_path, fonts_dir=None):
    from renderer.converter.convert import render_design_to_png
    warnings = render_design_to_png(design, assets_dir, str(png_path), fonts_dir=fonts_dir,
                                    max_size=max(design['canvas'].values()))
    # The import and render exceptions intentionally propagate: no box fallback.
    from PIL import Image
    with Image.open(png_path) as image:
        if image.format != 'PNG':
            raise ValueError('renderer did not produce PNG')
        if image.size != (design['canvas']['width'], design['canvas']['height']):
            raise ValueError('renderer PNG dimensions differ from requested canvas')
        image.verify()
    return warnings or []


def _json_write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def _remove_pair(paths):
    for path in paths:
        path.unlink(missing_ok=True)


def run_batch(input_dir, output_dir, assets_dir, fonts_dir=None):
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if input_dir.resolve() == output_dir.resolve():
        print(json.dumps({'status': 'failed', 'error': 'input and output directories must differ'}), file=sys.stderr)
        return 1
    assets_dir = Path(assets_dir).resolve()
    fonts_dir = Path(fonts_dir).resolve() if fonts_dir is not None else assets_dir.parent / 'fonts'
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = sorted(input_dir.glob('*.json'))
    if not tasks:
        print(json.dumps({'status': 'failed', 'error': f'No task files found in {input_dir}'}), file=sys.stderr)
        return 1
    failures = 0
    for task_path in tasks:
        started = time.perf_counter()
        record = {'task': task_path.name, 'status': 'failed', 'warnings': [], 'timings_seconds': {}}
        destinations = [output_dir / f'{task_path.stem}_output.json', output_dir / f'{task_path.stem}_output.png']
        try:
            _remove_pair(destinations)
            task = json.loads(task_path.read_text(encoding='utf-8'))
            if not isinstance(task, dict) or 'source' not in task or 'target_canvas' not in task:
                raise ValueError('task must contain source and target_canvas')
            source, target = task['source'], task['target_canvas']
            errors = validate_source(source) + validate_target(target)
            if errors:
                raise ValueError('; '.join(errors))
            original = copy.deepcopy(source)
            original_target = copy.deepcopy(target)
            resize_started = time.perf_counter()
            output, layout_diagnostics = resize_with_diagnostics(
                source, target, fonts_dir=fonts_dir, assets_dir=assets_dir)
            # Reject broken diagnostics before publishing a supposedly successful pair.
            json.dumps(layout_diagnostics, allow_nan=False)
            record['layout'] = layout_diagnostics
            record['timings_seconds']['resize'] = time.perf_counter() - resize_started
            if source != original or target != original_target:
                raise ValueError('resize mutated its input source or target_canvas')
            errors = validate_output(original, original_target, output)
            if errors:
                raise ValueError('; '.join(errors))
            with tempfile.TemporaryDirectory(prefix='.chameleon-', dir=output_dir) as temporary:
                staging = Path(temporary)
                staged_json, staged_png = staging / 'result.json', staging / 'result.png'
                _json_write(staged_json, output)
                render_started = time.perf_counter()
                warnings = list(render_to_png(output, assets_dir, staged_png, fonts_dir))
                json.dumps(warnings, allow_nan=False)
                record['warnings'] = warnings
                record['timings_seconds']['render'] = time.perf_counter() - render_started
                if not staged_png.is_file() or staged_png.stat().st_size == 0:
                    raise ValueError('renderer returned without producing a PNG')
                try:
                    os.replace(staged_json, destinations[0])
                    os.replace(staged_png, destinations[1])
                except Exception:
                    _remove_pair(destinations)
                    raise
            record['status'] = 'ok'
        except Exception as exc:
            failures += 1
            record['error'] = f'{type(exc).__name__}: {exc}'
            try:
                _remove_pair(destinations)
            except OSError as cleanup_error:
                record['cleanup_error'] = str(cleanup_error)
        record['timings_seconds']['total'] = time.perf_counter() - started
        # Diagnostics never enter the submitted design JSON. stderr is JSONL.
        print(json.dumps(record, ensure_ascii=False, allow_nan=False), file=sys.stderr)
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=Path('input'))
    parser.add_argument('--output-dir', type=Path, default=Path('output'))
    parser.add_argument('--assets-dir', type=Path, default=Path('brand_kit/assets'))
    parser.add_argument('--fonts-dir', type=Path, default=None,
                        help='Defaults to fonts/ beside assets directory')
    args = parser.parse_args(argv)
    return run_batch(args.input_dir, args.output_dir, args.assets_dir, args.fonts_dir)


if __name__ == '__main__':
    raise SystemExit(main())
