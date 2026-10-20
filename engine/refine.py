"""Bounded measured text growth around a validated incumbent.

Standalone text and supported text panels participate. Keep alignment anchors,
literal styles, group membership and all imagery. Local search
is deliberately incomplete and never claims a global optimum.
"""
from copy import deepcopy
from math import sqrt


def refine_text(source, design, units, backgrounds, measurer, assets_dir=None):
    from engine.resize import evaluate_candidate
    from engine.validation import validate_output

    W,H=design['canvas']['width'],design['canvas']['height']
    scale=max(1.,sqrt(W*H/(source['canvas']['width']*source['canvas']['height'])))
    eligible=[u.indices[0] for u in units if len(u.indices)==1
              and source['elements'][u.indices[0]]['type']=='text'
              and not source['elements'][u.indices[0]].get('rotation')]
    panels=[]
    for u in units:
        members=[source['elements'][i] for i in u.indices]
        shapes=[e for e in members if e['type']=='shape']
        if (len(members)>1 and len(shapes)==1 and shapes[0].get('shape_type')=='rectangle'
            and all(e['type'] in ('text','shape') and not e.get('rotation') for e in members)):
            panels.append(u)
    if not eligible and not panels or len(eligible)+len(panels)>24:return None
    current=deepcopy(design)
    score,quality=evaluate_candidate(source,current,backgrounds,measurer,assets_dir)
    original_score=score
    # Stable reading order resolves ties; names never define semantic roles.
    eligible.sort(key=lambda i:(current['elements'][i]['font_size'],
                                current['elements'][i]['y'],current['elements'][i]['x'],i))
    for i in eligible:
        old=current['elements'][i]
        if not old['content'].strip():continue
        align=old.get('text_align','left')
        anchor=old['x']+(old['width']/2 if align=='center' else old['width'] if align=='right' else 0)
        limit=2*min(anchor,W-anchor) if align=='center' else anchor if align=='right' else W-anchor
        # Nearest box edges supply useful local breakpoints. Actual ink and
        # source-aware collision checks, not these proposals, decide validity.
        widths={old['width'],limit}
        heights={old['height'],H-old['y']}
        for j,e in enumerate(current['elements']):
            if j==i or j in backgrounds:continue
            if old['y']<e['y']+e['height'] and e['y']<old['y']+old['height']:
                if align=='left' and e['x']>anchor:widths.add(e['x']-anchor-2)
                if align=='right' and e['x']+e['width']<anchor:widths.add(anchor-e['x']-e['width']-2)
            if old['x']<e['x']+e['width'] and e['x']<old['x']+old['width'] and e['y']>old['y']:
                heights.add(e['y']-old['y']-2)
        widths=sorted(w for w in widths if old['width']<=w<=limit)[:3]
        heights=sorted(h for h in heights if old['height']<=h<=H-old['y'])[:3]
        selected=None
        for width in widths:
            x=anchor-width/2 if align=='center' else anchor-width if align=='right' else anchor
            # A bottom anchor recovers space above footers without moving the
            # lower edge. Bound it by every overlapping neighbor, using the
            # proposed width so widening cannot jump across another column.
            bottom=old['y']+old['height']
            top=0.
            for j,e in enumerate(current['elements']):
                if j==i or j in backgrounds:continue
                if x<e['x']+e['width'] and e['x']<x+width and e['y']<bottom:
                    top=max(top,e['y']+e['height']+2)
            options=[(height,False) for height in heights]
            if bottom-top>old['height']:
                options.append((bottom-top,True))
            for height,from_bottom in options:
                trial,extent=measurer.fit(old,width,height,max(old['font_size'],source['elements'][i]['font_size']*scale))
                if trial['font_size']<=old['font_size'] or not extent.fits(width,height) or extent.missing_glyphs:continue
                ink_height=max(1.,extent.bottom+1)
                trial.update(x=x,y=bottom-ink_height if from_bottom else old['y'],width=width,height=ink_height)
                proposal=dict(current,elements=list(current['elements']))
                proposal['elements'][i]=trial
                if validate_output(source,design['canvas'],proposal):continue
                value,q=evaluate_candidate(source,proposal,backgrounds,measurer,assets_dir)
                if (q['collision_proxy']>quality['collision_proxy']+1e-6
                    or q['text_overflow_px']>quality['text_overflow_px']+1e-6
                    or q['canvas_ink_overflow_px']>quality['canvas_ink_overflow_px']+1e-6
                    or q['hierarchy_inversion']>quality['hierarchy_inversion']+1e-6
                    or q['missing_glyphs']>quality['missing_glyphs']):continue
                if value>score+1e-6:
                    selected=(proposal,value,q)
                    score=value
        if selected:current,score,quality=selected
    # Reflow an existing support panel within its current horizontal footprint.
    # Grow downward only into unoccupied space; do not create a new backing.
    from engine.flow import _choices
    for unit in panels:
        members=[current['elements'][i] for i in unit.indices]
        x=min(e['x'] for e in members);y=min(e['y'] for e in members)
        width=max(e['x']+e['width'] for e in members)-x
        bottom=H
        for j,e in enumerate(current['elements']):
            if j in unit.indices or j in backgrounds:continue
            if e['x']<x+width and x<e['x']+e['width'] and e['y']>y:
                bottom=min(bottom,e['y']-2)
        height=bottom-y
        if min(width,height)<=0:continue
        base=min(source['elements'][i]['font_size'] for i in unit.indices if source['elements'][i]['type']=='text')
        selected=None
        for floor in (8,12,16,20,24):
            for state in _choices(source,unit,width,height,floor,base,scale,.5,measurer):
                proposal=dict(current,elements=list(current['elements']))
                if any(e['type']=='text' and e['font_size']<current['elements'][i]['font_size']
                       for i,e in state.placements.items()):continue
                if not any(e['type']=='text' and e['font_size']>current['elements'][i]['font_size']
                           for i,e in state.placements.items()):continue
                for i,e in state.placements.items():proposal['elements'][i]=dict(e,x=e['x']+x,y=e['y']+y)
                if validate_output(source,design['canvas'],proposal):continue
                value,q=evaluate_candidate(source,proposal,backgrounds,measurer,assets_dir)
                if any(q[k]>quality[k]+1e-6 for k in ('collision_proxy','text_overflow_px',
                       'canvas_ink_overflow_px','missing_glyphs','hierarchy_inversion')):continue
                if value>score+1e-6:selected=(proposal,value,q);score=value
        if selected:current,score,quality=selected
    return current if score>original_score+1e-6 else None
