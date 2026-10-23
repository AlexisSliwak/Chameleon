"""Paired local benchmark; same cases and outputs, no official scoring claims."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.resize import resize_with_diagnostics
from engine.validation import validate_output
from renderer.converter.convert import _get_renderer,convert_chameleon_to_crello


def run(output, mode, repeats):
    root=Path('/app');output.mkdir(parents=True,exist_ok=False);os.environ['CHAMELEON_ADVISOR']=mode
    tasks=[(p.stem,json.loads(p.read_text())) for p in sorted((root/'input').glob('*.json'))]
    for family in ('editorial-event','rotated-workshop','transparent-hero'):
        task=json.loads((root/'tests/fixtures/design-families'/(family+'.json')).read_text())
        task['target_canvas']={'width':728,'height':90};tasks.append((family,task))
    for family in ('color-alpha','token-and-glyph-pressure'):
        task=json.loads((root/'tests/fixtures/extreme-challenges'/(family+'.json')).read_text())
        task['target_canvas']={'width':600,'height':300};tasks.append((family,task))
    (output/'cases.json').write_text(json.dumps(tasks,indent=2))
    renderer=_get_renderer(str(root/'brand_kit/fonts'));rows=[]
    for repeat in range(repeats):
        for name,task in tasks:
            original=deepcopy(task);started=time.perf_counter()
            design,diagnostics=resize_with_diagnostics(task['source'],task['target_canvas'])
            elapsed=time.perf_counter()-started
            errors=validate_output(task['source'],task['target_canvas'],design)
            assert task==original and not errors,(name,errors)
            artifact=str(repeat)+'-'+name
            (output/(artifact+'.json')).write_text(json.dumps(design,sort_keys=True))
            ex,warnings=convert_chameleon_to_crello(design,renderer.font_manager,str(root/'brand_kit/assets'))
            png=renderer.render(ex,max_size=max(design['canvas'].values()),format='png')
            (output/(artifact+'.png')).write_bytes(png)
            rows.append(dict(case=name,repeat=repeat,resize_seconds=elapsed,png_sha256=hashlib.sha256(png).hexdigest(),diagnostics=diagnostics,warnings=warnings))
            (output/'results.json').write_text(json.dumps(dict(mode=mode,repeats=repeats,rows=rows,process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,engine_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'engine').glob('*.py')}),indent=2))
            print(mode,repeat,name,round(elapsed,3),flush=True)
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Path benchmark</title><h1>'+mode+' benchmark</h1><p>Development cases, not held-out evaluation. Native PNGs linked below.</p>'+''.join('<p><a href="0-'+name+'.png">'+name+'</a></p>' for name,_ in tasks))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--mode',choices=['off','regions'],required=True);parser.add_argument('--repeats',type=int,default=2)
    args=parser.parse_args()
    if args.repeats<1:parser.error('repeats must be positive')
    run(args.output_dir,args.mode,args.repeats)
