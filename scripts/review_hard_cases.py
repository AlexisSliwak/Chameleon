"""Render advanced stress cases through the production CLI for manual review.

Never changes the engine. Each case has an isolated process and a local harness
timeout (not an official hackathon limit). Failed cases remain in the gallery.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.review_gallery import write_gallery


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def load_suite(directory):
    suite = json.loads((directory/'suite.json').read_text(encoding='utf-8'))
    if not suite.get('families'):
        raise ValueError('suite must contain families')
    seen = set()
    families = []
    for family in suite['families']:
        filename = family['file']
        if not re.fullmatch(r'[a-z0-9-]+\.json', filename) or filename in seen:
            raise ValueError('fixture names must be unique simple JSON filenames')
        seen.add(filename)
        if not (directory/filename).resolve().is_relative_to(directory.resolve()):
            raise ValueError('fixture escapes suite directory')
        task = json.loads((directory/filename).read_text(encoding='utf-8'))
        targets = family['targets']
        target_names = [t['name'] for t in targets]
        if not targets or len(target_names) != len(set(target_names)):
            raise ValueError('targets must have unique names')
        for target in targets:
            if not re.fullmatch(r'[a-z0-9-]+', target['name']):
                raise ValueError('target name must be a simple identifier')
            canvas = target['canvas']
            if set(canvas) != {'width','height'} or any(type(v) is not int or v <= 0 for v in canvas.values()):
                raise ValueError('target canvas must have positive integer dimensions')
        families.append((family,task))
    return suite,families


def preservation_errors(source, target, output):
    """Independent identity/content/style check, separate from the engine report."""
    editable = {'x','y','width','height','font_size'}
    errors = []
    if not isinstance(output,dict) or output.get('canvas') != target:
        errors.append('Requested canvas differs')
    if not isinstance(output,dict) or not isinstance(output.get('elements'),list):
        return errors+['Missing element list']
    old,new = source['elements'],output['elements']
    if Counter(e['id'] for e in old) != Counter(e.get('id') for e in new):
        return errors+['Element ID multiset differs']
    originals = {e['id']:e for e in old}
    for e in new:
        before = originals[e['id']]
        if {k:v for k,v in before.items() if k not in editable} != {k:v for k,v in e.items() if k not in editable}:
            errors.append('Content, asset or immutable style changed: '+e['id'])
    return errors


def quality_flags(layout):
    flags = []
    minimum = layout.get('minimum_font_size')
    if minimum is not None and minimum < 8:
        flags.append('Very small type: below 8px')
    elif minimum is not None and minimum < 12:
        flags.append('Small type: below 12px')
    for field,label,threshold in [('text_overflow_px','Measured text overflow',.75),
                                  ('canvas_ink_overflow_px','Ink outside canvas',.01),
                                  ('missing_glyphs','Missing font glyphs',0),
                                  ('collision_proxy','Possible content collision',.05)]:
        if layout.get(field,0)>threshold:
            flags.append(label)
    raster=layout.get('raster',{})
    if max(raster.get('low_contrast_proxy',0),raster.get('sampled_low_contrast_proxy',0))>.05:
        flags.append('Possible low contrast')
    return flags


def execute(command, timeout, cwd):
    start = time.perf_counter()
    try:
        result = subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=timeout)
        return dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,
                    timed_out=False,seconds=time.perf_counter()-start)
    except subprocess.TimeoutExpired as exc:
        decode = lambda value: value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value or ''
        return dict(returncode=None,stdout=decode(exc.stdout),stderr=decode(exc.stderr),
                    timed_out=True,seconds=time.perf_counter()-start)
    except OSError as exc:
        return dict(returncode=None,stdout='',stderr=type(exc).__name__+': '+str(exc),
                    timed_out=False,seconds=time.perf_counter()-start)


def evaluate_case(family, task, target, run, timeout, assets, fonts):
    from engine.validation import validate_output
    from PIL import Image
    case_id = Path(family['file']).stem+'--'+target['name']
    folder = run/'cases'/case_id
    (folder/'input').mkdir(parents=True)
    payload = dict(source=deepcopy(task['source']),target_canvas=deepcopy(target['canvas']))
    input_path = folder/'input/task.json'
    save(input_path,payload)
    before = digest(input_path)
    command = [sys.executable,'-m','engine.main','--input-dir',str(folder/'input'),
               '--output-dir',str(folder/'output'),'--assets-dir',str(assets),'--fonts-dir',str(fonts)]
    execution = execute(command,timeout,ROOT)
    (folder/'stdout.log').write_text(execution.pop('stdout'),encoding='utf-8')
    stderr = execution.pop('stderr')
    (folder/'stderr.log').write_text(stderr,encoding='utf-8')
    row = dict(id=case_id,family=family['name'],fixture=family['file'],target=target['canvas'],
               target_name=target['name'],pressure=target['pressure'],tags=family['tags'],
               review=family['review'],source_png='sources/'+Path(family['file']).stem+'.png',
               source_canvas=task['source']['canvas'],element_count=len(task['source']['elements']),
               command=command,execution=execution,status='failed',errors=[],flags=[],warnings=[],
               input_sha256=before,log=(folder/'stderr.log').relative_to(run).as_posix())
    if digest(input_path)!=before:
        row['errors'].append('Engine modified input file')
    if execution['timed_out']:
        row['errors'].append('Harness timeout; not an official hackathon limit')
    elif execution['returncode']!=0:
        row['errors'].append('Production runner exited unsuccessfully')
    for line in stderr.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record,dict) and record.get('task')=='task.json':
            row['diagnostics'] = record.get('layout',{})
            row['warnings'] = record.get('warnings',[])
            if record.get('error'):
                row['errors'].append(record['error'])
    output_json,output_png = folder/'output/task_output.json',folder/'output/task_output.png'
    try:
        design = json.loads(output_json.read_text(encoding='utf-8'))
        row['json'] = output_json.relative_to(run).as_posix()
        row['errors'] += preservation_errors(payload['source'],payload['target_canvas'],design)
        row['errors'] += validate_output(payload['source'],payload['target_canvas'],design)
        with Image.open(output_png) as image:
            image.load()
            if image.format!='PNG' or image.size!=(target['canvas']['width'],target['canvas']['height']):
                row['errors'].append('PNG format or native dimensions differ')
        row['png'] = output_png.relative_to(run).as_posix()
        row['output_sha256'] = dict(json=digest(output_json),png=digest(output_png))
        row['flags'] = quality_flags(row.get('diagnostics',{}))
        if not row['errors']:
            row['status'] = 'review' if row['flags'] else 'checks-passed'
    except Exception as exc:
        row['errors'].append(type(exc).__name__+': '+str(exc))
    save(folder/'result.json',row)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--suite-dir',type=Path,default=ROOT/'tests/fixtures/hard-challenges')
    parser.add_argument('--timeout',type=float,default=120,help='Per-case harness budget in seconds, not official scoring')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout<=0:
        parser.error('--timeout must be positive and finite')
    if args.output_dir.exists():
        parser.error('--output-dir must not exist; earlier evidence is preserved')
    suite_dir = args.suite_dir.resolve()
    try:
        suite,families = load_suite(suite_dir)
    except (ValueError,KeyError,OSError,TypeError) as exc:
        parser.error(str(exc))
    from engine.validation import validate_source
    from engine.main import render_to_png
    assets,fonts = ROOT/'brand_kit/assets',ROOT/'brand_kit/fonts'
    for family,task in families:
        errors = validate_source(task['source'])
        missing = sorted({e['asset_id'] for e in task['source']['elements'] if e['type']=='image' and not (assets/e['asset_id']).is_file()})
        if errors or missing!=sorted(family['expected_missing_assets']):
            parser.error(family['file']+': invalid source or unexpected missing assets '+str(errors+missing))
    run = args.output_dir.resolve()
    run.mkdir(parents=True,exist_ok=False)
    (run/'sources').mkdir()
    (run/'inputs').mkdir()
    for path in suite_dir.glob('*.json'):
        shutil.copyfile(path,run/'inputs'/path.name)
    code = {p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'engine').glob('*.py'))}
    manifest = dict(created_utc=datetime.now(timezone.utc).isoformat(),suite=suite,
                    suite_sha256=digest(suite_dir/'suite.json'),
                    fixture_sha256={f['file']:digest(suite_dir/f['file']) for f,t in families},
                    engine_sha256=code,python=sys.version,platform=platform.platform(),
                    timeout_seconds=args.timeout,entrypoint='python -m engine.main',
                    interpretation='Local engineering checks; manual review required. Not an official score.',
                    warning_thresholds=dict(very_small_font_px=8,small_font_px=12,collision_proxy=.05,low_contrast_proxy=.05),
                    asset_sha256={p.name:digest(p) for p in assets.glob('*') if p.is_file()},
                    font_sha256={p.relative_to(fonts).as_posix():digest(p) for p in fonts.rglob('*') if p.is_file()})
    # Freeze harness files as well as fixture/engine hashes before execution.
    (run/'harness').mkdir()
    for path in [Path(__file__),ROOT/'scripts/review_gallery.py',*sorted((ROOT/'scripts/review_assets').glob('*'))]:
        shutil.copyfile(path,run/'harness'/path.name)
    manifest['harness_sha256'] = {p.name:digest(p) for p in (run/'harness').iterdir()}
    save(run/'manifest.json',manifest)
    run_id = digest(run/'manifest.json')
    rows,sources = [],{}
    for family,task in families:
        key = family['file']
        try:
            warnings = render_to_png(task['source'],assets,run/'sources'/(Path(key).stem+'.png'),fonts)
            sources[key] = dict(status='rendered',warnings=warnings)
        except Exception as exc:
            sources[key] = dict(status='failed',error=type(exc).__name__+': '+str(exc))
        for target in family['targets']:
            row = evaluate_case(family,task,target,run,args.timeout,assets,fonts)
            if sources[key]['status']=='failed':
                row['source_error'] = sources[key]['error']
            rows.append(row)
            save(run/'results.json',dict(run_id=run_id,sources=sources,cases=rows))
            write_gallery(run,manifest,rows,run_id)
            print(json.dumps(dict(case=row['id'],status=row['status'],seconds=round(row['execution']['seconds'],2))),flush=True)
    unchanged = all((ROOT/p).is_file() and digest(ROOT/p)==value for p,value in code.items())
    unchanged &= all((suite_dir/p).is_file() and digest(suite_dir/p)==value for p,value in manifest['fixture_sha256'].items())
    unchanged &= digest(suite_dir/'suite.json')==manifest['suite_sha256']
    unchanged &= all((assets/p).is_file() and digest(assets/p)==value for p,value in manifest['asset_sha256'].items())
    unchanged &= all((fonts/p).is_file() and digest(fonts/p)==value for p,value in manifest['font_sha256'].items())
    summary = dict(cases=len(rows),contract_passes=sum(r['status']!='failed' for r in rows),
                   failures=sum(r['status']=='failed' for r in rows),visual_review_flags=sum(bool(r['flags']) for r in rows),
                   source_render_failures=sum(s['status']=='failed' for s in sources.values()),
                   hashes_unchanged=unchanged,manual_review='not performed by automated checks',run_id=run_id)
    save(run/'summary.json',summary)
    print(json.dumps(summary,indent=2))
    return int(bool(summary['failures'] or summary['source_render_failures'] or not unchanged))


if __name__=='__main__':
    raise SystemExit(main())
