"""Rendered component ablation with actual guards; synthetic controls, not a benchmark."""
import argparse
import hashlib
from pathlib import Path
import json
import sys
import shutil
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_region_repairs import fixture,evaluator,FONTS
from tests.test_semantics import FakeModel
from engine.semantics import select_with_semantics,region_visibility,annotate_assets,_CACHE
from renderer.converter.convert import _get_renderer,convert_chameleon_to_crello


def run(output):
    output.mkdir(parents=True,exist_ok=False);assets=output/'assets';assets.mkdir()
    renderer=_get_renderer(str(FONTS));rows=[];report=[]
    for kind in ('occlusion','crop','group','bottle'):
        source,baseline=fixture(assets,kind)
        if kind=='bottle':
            shutil.copyfile(Path('brand_kit/assets/solstice_bottle.png'),assets/'subject.png')
            source=dict(canvas=dict(width=400,height=400),elements=[
                dict(id='product',type='image',asset_id='subject.png',fit='contain',x=100,y=60,width=200,height=280,z_index=0),
                dict(id='panel',type='shape',shape_type='rectangle',fill_color='rgba(245,230,200,1)',x=0,y=360,width=400,height=40,z_index=1)])
            from copy import deepcopy
            baseline=deepcopy(source);baseline['elements'][1]['y']=180
        evaluate=evaluator(source,assets);old=evaluate('baseline',baseline)
        started=time.monotonic();_CACHE.clear()
        result,info=select_with_semantics(source,old,[],FONTS,assets,mode='regions',model=FakeModel([]),evaluate=evaluate)
        annotation,_=annotate_assets(source,assets,FakeModel([]))
        before=region_visibility(baseline,annotation,FONTS,assets)['elements'][0]['retained']
        after=region_visibility(result[2],annotation,FONTS,assets)['elements'][0]['retained']
        report.append(dict(case=kind,before_retention=before,after_retention=after,seconds=time.monotonic()-started,diagnostics=info))
        assert after>.98 and after-before>.3
        for label,design in (('source',source),('before',baseline),('after',result[2])):
            name=kind+'-'+label
            (output/(name+'.json')).write_text(json.dumps(design,indent=2))
            example,_=convert_chameleon_to_crello(design,renderer.font_manager,str(assets))
            (output/(name+'.png')).write_bytes(renderer.render(example,format='png'))
        rows.append('<tr><th>'+kind+'</th>'+''.join('<td><img src="'+kind+'-'+label+'.png"><br>'+label+'</td>' for label in ('source','before','after'))+'</tr>')
    (output/'results.json').write_text(json.dumps(dict(kind='Synthetic component ablation; real renderer and quality guards; no model calls',cases=report,engine_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('engine').glob('*.py')}),indent=2))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Region repair controls</title><style>body{font:16px system-ui;margin:2rem}td{padding:1rem}img{border:1px solid #888}</style><h1>Region repair controls</h1><p>Synthetic component ablation with actual renderer and safety guards. Source, pre-repair incumbent, and automatically selected repair. Not held-out human evidence.</p><table>'+''.join(rows)+'</table>')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True,type=Path)
    run(parser.parse_args().output_dir)
