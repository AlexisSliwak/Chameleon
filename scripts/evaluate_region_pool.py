"""Render early-pool and background-subject component controls."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_region_repairs import fixture,evaluator,FONTS
from engine.semantics import prepare_region_pool,select_with_semantics,region_visibility
from renderer.converter.convert import _get_renderer,convert_chameleon_to_crello


def run(output):
    output.mkdir(parents=True,exist_ok=False);assets=output/'assets';assets.mkdir()
    os.environ['CHAMELEON_ADVISOR']='regions';renderer=_get_renderer(str(FONTS));results=[];html=[]
    for kind in ('outside-shortlist','background-subject'):
        source,seed=fixture(assets)
        if kind=='background-subject':
            source['elements'][0].update(x=0,y=0,width=240,height=200,fit='cover')
            seed=deepcopy(source);seed['elements'][1].update(x=100,y=50)
        baseline=deepcopy(seed)
        if kind=='outside-shortlist':baseline['elements'][1].update(x=0,y=0,width=240,height=200)
        evaluate=evaluator(source,assets);old=evaluate('incumbent',baseline)
        proposals,context=prepare_region_pool(source,[evaluate('source-fit',seed)],FONTS,assets)
        guided=[evaluate(method,d) for method,d in proposals]
        result,info=select_with_semantics(source,old,[],FONTS,assets,mode='regions',evaluate=evaluate,context=context,guided=guided)
        before=region_visibility(baseline,context['annotations'],FONTS,assets)['loss']
        after=region_visibility(result[2],context['annotations'],FONTS,assets)['loss']
        assert info['status']=='selected' and after<.02 and before-after>.1
        results.append(dict(case=kind,before_loss=before,after_loss=after,diagnostics=info))
        for label,d in [('source',source),('before',baseline),('after',result[2])]:
            name=kind+'-'+label;(output/(name+'.json')).write_text(json.dumps(d,indent=2))
            ex,_=convert_chameleon_to_crello(d,renderer.font_manager,str(assets))
            (output/(name+'.png')).write_bytes(renderer.render(ex,format='png'))
        html.append('<tr><th>'+kind+'</th>'+''.join('<td><img src="'+kind+'-'+label+'.png"><br>'+label+'</td>' for label in ('source','before','after'))+'</tr>')
    (output/'results.json').write_text(json.dumps(results,indent=2))
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Region pool controls</title><style>body{font:16px system-ui;margin:2rem}td{padding:1rem}img{border:1px solid #aaa}</style><h1>Region pool controls</h1><p>Constructed component controls using the real renderer and quality guards. These are not held-out end-to-end wins.</p><table>'+''.join(html)+'</table>')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True,type=Path)
    run(parser.parse_args().output_dir)
