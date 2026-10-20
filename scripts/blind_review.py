"""Create anonymous local PNG pairs and summarize independently entered CSV ratings.

The answer key stays outside the reviewer directory. No ratings are invented.
This compares supplied runs, not competitors or official scores.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import shutil

FIELDS=['case','preference','readability','faithfulness','hierarchy','severe_failure','notes']


def case_key(row):
    return row.get('id') or row['fixture']+' '+json.dumps(row['target'],sort_keys=True)


def rows(directory):
    result={}
    data=json.loads((directory/'results.json').read_text())
    for row in data['cases']:
        row=dict(row)
        if 'source_png' not in row:
            row['source_png']=data.get('source_previews',{}).get(row.get('fixture'),{}).get('png')
        key=case_key(row)
        if key in result:raise ValueError('duplicate case: '+key)
        result[key]=row
    return result


def create(before,after,output,seed=0):
    old,new=rows(before),rows(after)
    if set(old)!=set(new):raise ValueError('runs must contain exactly the same cases')
    # Preflight every file before creating output; missing or failed cases are
    # explicit errors, never silently dropped from a favorable comparison.
    for directory,run in ((before,old),(after,new)):
        for row in run.values():
            for field in ('png','json','source_png'):
                path=(directory/row[field]).resolve()
                if not path.is_relative_to(directory.resolve()):raise ValueError('path escapes run')
                if not path.is_file():raise ValueError('missing output: '+str(path))
    for k in old:
        if (before/old[k]['source_png']).read_bytes()!=(after/new[k]['source_png']).read_bytes():
            raise ValueError('source previews differ: '+k)
    output.mkdir(parents=True,exist_ok=False)
    reviewer=output/'reviewer';reviewer.mkdir()
    rng=random.Random(seed);order=sorted(old);rng.shuffle(order)
    key=[]
    parts=['<!doctype html><meta charset="utf-8"><title>Anonymous design review</title>',
           '<style>body{font:16px system-ui;margin:32px}section{border-top:1px solid #aaa;padding:24px 0}.pair{display:flex;gap:24px}figure{margin:0;max-width:48%}img{max-width:100%}a{color:#164e63}</style>',
           '<h1>Anonymous design review</h1><p>Open PNGs at native size. Compare readable copy, faithful content/branding and visual hierarchy. Record A, B, tie or neither in ratings.csv; leave unseen cases blank. Some pairs are identical controls. Do not infer a method from placement.</p>',
           '<p>Readability, faithfulness and hierarchy use the same A/B/tie/neither scale. Severe failure: A, B, both or none. Notes are free text. These are development designs, not hidden competition tests.</p>']
    for index,k in enumerate(order,1):
        name=f'case-{index:03d}';flip=rng.choice([False,True])
        sources=[(before,old[k],'before'),(after,new[k],'after')]
        if flip:sources.reverse()
        mapping={}
        source_name=f'{name}-source.png'
        shutil.copyfile(before/old[k]['source_png'],reviewer/source_name)
        parts.append(f'<section><h2>{name}</h2><details><summary>Source design</summary><a href="{source_name}"><img style="max-width:600px;max-height:500px" src="{source_name}" alt="Source"></a></details><div class="pair">')
        for label,(directory,row,method) in zip(('A','B'),sources):
            src=directory/row['png'];dest=reviewer/f'{name}-{label}.png';shutil.copyfile(src,dest)
            mapping[label]=dict(method=method,sha256=hashlib.sha256(src.read_bytes()).hexdigest())
            parts.append(f'<figure><figcaption>{label}</figcaption><a href="{dest.name}"><img src="{dest.name}" alt="{name} {label}"></a></figure>')
        parts.append('</div></section>')
        family=old[k].get('fixture') or k.split('--')[0]
        key.append(dict(case=name,source_case=k,family=family,labels=mapping))
    (reviewer/'index.html').write_text('\n'.join(parts),encoding='utf-8')
    with (reviewer/'ratings.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader()
        writer.writerows(dict(case=r['case']) for r in key)
    (output/'answer-key.json').write_text(json.dumps(dict(seed=seed,before=str(before.resolve()),after=str(after.resolve()),cases=key),indent=2)+'\n')
    return key


def summarize(key_file,ratings):
    key=json.loads(key_file.read_text());cases={r['case']:r for r in key['cases']}
    counts=dict(before=0,after=0,tie=0,neither=0,unrated=0)
    families={};seen=set();severe=[]
    dimensions={name:dict(before=0,after=0,tie=0,neither=0,unrated=0) for name in ('readability','faithfulness','hierarchy')}
    with ratings.open(newline='') as f:
        for row in csv.DictReader(f):
            name=row['case']
            if name not in cases or name in seen:raise ValueError('unknown or duplicate case: '+name)
            seen.add(name);item=cases[name]
            for field in ('preference','readability','faithfulness','hierarchy'):
                if row[field] not in ('','A','B','tie','neither'):raise ValueError('invalid rating: '+field)
            if row['severe_failure'] not in ('','A','B','both','none'):raise ValueError('invalid severe failure')
            choice=row['preference']
            outcome=item['labels'][choice]['method'] if choice in ('A','B') else choice or 'unrated'
            counts[outcome]+=1
            families.setdefault(item['family'],dict(before=0,after=0,tie=0,neither=0,unrated=0))[outcome]+=1
            for field in dimensions:
                vote=row[field]
                decoded=item['labels'][vote]['method'] if vote in ('A','B') else vote or 'unrated'
                dimensions[field][decoded]+=1
            if row['severe_failure'] in ('A','B','both'):
                affected=['before','after'] if row['severe_failure']=='both' else [item['labels'][row['severe_failure']]['method']]
                severe.append(dict(case=name,methods=affected,notes=row['notes']))
    if seen!=set(cases):raise ValueError('ratings must retain every assigned case, including blanks')
    return dict(counts=counts,families=families,dimensions=dimensions,severe_failures=severe,
                interpretation='Entered human ratings only; shared-family trials, not independent case votes or competition rank.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('create')
    for name in ('before','after','output'):build.add_argument('--'+name,type=Path,required=True)
    build.add_argument('--seed',type=int,default=0)
    score=sub.add_parser('summarize');score.add_argument('--key',type=Path,required=True);score.add_argument('--ratings',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='create':print(json.dumps({'cases':len(create(args.before,args.after,args.output,args.seed)),'reviewer_directory':str(args.output/'reviewer')}))
    else:print(json.dumps(summarize(args.key,args.ratings),indent=2))


if __name__=='__main__':main()
