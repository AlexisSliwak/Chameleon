"""Offline semantic calibration with independent sessions and rendered artifacts.

Known controls establish behavior, not held-out human preference or winning scores.
Runtime failures remain explicit evidence; contract failures make the harness fail.
"""
import argparse
from copy import deepcopy
import hashlib
import html
import json
import os
from pathlib import Path
import resource
import sys
import time
from PIL import Image, ImageDraw, ImageChops
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine.local_model as local
from engine.local_model import ModelUnavailable
from engine.semantics import annotate_assets, compare_layouts, region_visibility, _preview, _CACHE, REGION_PROMPT, REGION_SCHEMA, validate_region
from engine.resize import resize_with_diagnostics
from engine.validation import validate_output


def run(destination, controls_only=False):
    root=Path('/app');assets=root/'brand_kit/assets';fonts=root/'brand_kit/fonts'
    paths=sorted((root/'input').glob('*.json'))
    if not paths and not controls_only:raise ValueError('No input tasks; mount the input directory')
    destination.mkdir(parents=True,exist_ok=False)
    report=dict(kind='development calibration, not held-out',controls_only=controls_only,trials=[],sessions=[],started=time.time())
    report['engine_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'engine').glob('*.py'))}
    report['input_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    manifest=Path(os.environ.get('CHAMELEON_MODEL_DIR','/opt/chameleon-model'))/'manifest.json'
    report['model_manifest']=json.loads(manifest.read_text()) if manifest.is_file() else None
    harness=Path(__file__).read_bytes();(destination/'harness.py').write_bytes(harness)
    report['harness_sha256']=hashlib.sha256(harness).hexdigest()
    rows=[];model=None;session=None;contract_errors=[]

    def finish_session():
        if model is None:return
        model.close()
        report['sessions'].append(dict(name=session,calls=model.calls,seconds=model.seconds,failure=model.failure))
        if model.last_log:(destination/(session+'-runtime.log')).write_text(model.last_log)

    def begin_session(name):
        nonlocal model,session
        finish_session();model=local.LocalModel();session=name
        local._MODEL=model;_CACHE.clear()

    def save():
        (destination/'results.json').write_text(json.dumps(report,indent=2))

    try:
        source=dict(canvas=dict(width=400,height=400),elements=[
            dict(id='product',type='image',asset_id='solstice_bottle.png',fit='contain',x=100,y=60,width=200,height=280,z_index=0),
            dict(id='panel',type='shape',shape_type='rectangle',fill_color='rgba(245,230,200,1)',x=0,y=360,width=400,height=40,z_index=1)])
        blocked=deepcopy(source);blocked['elements'][1].update(x=100,y=60,width=200,height=280)
        for name,d in (('control-source',source),('control-blocked',blocked),('control-clear',source)):
            _preview(d,fonts,assets).save(destination/(name+'.png'))
            (destination/(name+'.json')).write_text(json.dumps(d,indent=2));rows.append(name)

        begin_session('region-control')
        started=time.monotonic();phase='region control'
        try:
            regions,trace=annotate_assets(source,assets,model)
            report['regions']=trace
            visibility={name:region_visibility(d,regions,fonts,assets) for name,d in [('blocked',blocked),('clear',source)]}
            report['visibility']=visibility
            passed=bool(regions and visibility['blocked']['loss']>visibility['clear']['loss']+.5)
            report['trials'].append(dict(name='region control',passed=passed,seconds=time.monotonic()-started))
            for i,(asset_id,region) in enumerate(regions.items()):
                with Image.open(assets/asset_id) as original:
                    rgba=original.convert('RGBA');image=Image.new('RGBA',rgba.size,(128,128,128,255));image.alpha_composite(rgba);image=image.convert('RGB')
                box=region['box'];ImageDraw.Draw(image).rectangle((box[0]*image.width,box[1]*image.height,box[2]*image.width,box[3]*image.height),outline='red',width=4)
                name='asset-region-'+str(i);image.save(destination/(name+'.png'))
                (destination/(name+'.json')).write_text(json.dumps(dict(asset_id=asset_id,region=region),indent=2));rows.append(name)
            # Transparent assets use exact alpha support. Separately test the
            # model on an opaque composite, with known original foreground mask.
            started=time.monotonic();phase='opaque subject coverage'
            with Image.open(assets/'solstice_bottle.png') as original:
                rgba=original.convert('RGBA');alpha=rgba.getchannel('A')
                opaque=Image.new('RGBA',rgba.size,(128,128,128,255));opaque.alpha_composite(rgba)
            preview=opaque.convert('RGB');preview.thumbnail((448,448))
            raw=model.ask(REGION_PROMPT,[preview],REGION_SCHEMA);region=validate_region(raw)
            coverage=0.;fraction=0.
            if region:
                l,t,r,b=region['box'];mask=Image.new('L',rgba.size,0)
                ImageDraw.Draw(mask).rectangle((int(l*rgba.width),int(t*rgba.height),max(0,int(r*rgba.width)-1),max(0,int(b*rgba.height)-1)),fill=255)
                total=sum(i*n for i,n in enumerate(alpha.histogram()))
                kept=sum(i*n for i,n in enumerate(ImageChops.multiply(alpha,mask).histogram()))
                coverage=kept/total if total else 0.;fraction=(r-l)*(b-t)
                ImageDraw.Draw(preview).rectangle((l*preview.width,t*preview.height,r*preview.width,b*preview.height),outline='red',width=2)
            name='opaque-subject-control';preview.save(destination/(name+'.png'))
            record=dict(name='opaque subject coverage',raw=raw,foreground_coverage=coverage,box_fraction=fraction,
                        passed=coverage>=.95,seconds=time.monotonic()-started,
                        limitation='Coverage only; a whole-image box is safe but supplies no useful localization precision.')
            report['trials'].append(record);(destination/(name+'.json')).write_text(json.dumps(record,indent=2));rows.append(name)
        except ModelUnavailable as exc:
            report['trials'].append(dict(name=phase,passed=False,failure=str(exc),seconds=time.monotonic()-started))
        save()

        begin_session('critic-control')
        for name,a,b,expected in [('clear versus hidden product',blocked,source,True),('identical candidates',source,source,False)]:
            started=time.monotonic()
            try:
                accepted,votes=compare_layouts(source,a,b,fonts,assets,model)
                policy_pass=accepted==expected
                model_pass=accepted if expected else all(v['winner'] in ('tie','abstain') for v in votes)
                report['trials'].append(dict(name=name,accepted=accepted,expected=expected,passed=policy_pass and model_pass,
                    policy_pass=policy_pass,model_pass=model_pass,votes=votes,seconds=time.monotonic()-started))
            except ModelUnavailable as exc:
                report['trials'].append(dict(name=name,passed=False,failure=str(exc),seconds=time.monotonic()-started))
            save()

        # Fresh session/cache per condition. Batch tasks share only their own
        # condition's runtime, matching production cold-start then warm reuse.
        for mode in (() if controls_only else ('off','regions','critic','both')):
            begin_session('batch-'+mode);os.environ['CHAMELEON_ADVISOR']=mode
            for index,path in enumerate(paths):
                task=json.loads(path.read_text());before=deepcopy(task)
                started=time.monotonic();calls=model.calls;seconds=model.seconds
                loaded=model.process is not None and model.process.poll() is None
                output,diagnostics=resize_with_diagnostics(task['source'],task['target_canvas'],fonts,assets)
                errors=validate_output(task['source'],task['target_canvas'],output)
                if task!=before:errors.append('input mutation')
                name=path.stem+'-'+mode
                (destination/(name+'.json')).write_text(json.dumps(output,indent=2))
                _preview(output,fonts,assets).save(destination/(name+'.png'));rows.append(name)
                report['trials'].append(dict(name=name,mode=mode,batch_position=index,model_previously_loaded=loaded,
                    model_calls=model.calls-calls,model_seconds=model.seconds-seconds,seconds=time.monotonic()-started,
                    errors=errors,diagnostics=diagnostics))
                contract_errors.extend(dict(name=name,error=error) for error in errors);save()
    finally:
        finish_session()
        report.update(elapsed_seconds=time.time()-report['started'],contract_errors=contract_errors,
                      child_peak_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                      process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        save()
        (destination/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Semantic calibration</title><style>body{font:16px system-ui;margin:2rem}main{display:flex;flex-wrap:wrap;gap:20px}figure{margin:0;width:400px}img{max-width:100%;border:1px solid #999}</style><h1>Offline semantic calibration</h1><p>Known development controls; fresh model session per condition. Inspect raw votes, control failures, timings and safety diagnostics in <a href="results.json">results.json</a>. Images are previews; JSON retains exact geometry. A fallback is not successful model inference.</p><main>'+''.join('<figure><figcaption>'+html.escape(n)+'</figcaption><a href="'+n+'.json"><img src="'+n+'.png"></a></figure>' for n in rows)+'</main>')
    if contract_errors:raise ValueError('Contract failures; see results.json')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--controls-only',action='store_true')
    args=parser.parse_args();run(args.output_dir,args.controls_only)
