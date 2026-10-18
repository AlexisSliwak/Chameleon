"""Measured, ordered line packing with shared typography tiers.

Choose text sizes before allocating rectangles. A bounded frontier solves each
contiguous row; dynamic programming selects line breaks without permuting the
source's reading sequence. This is an additional hypothesis, not a universal
interpretation of an arbitrary source or an exact continuous optimizer.
"""
from math import sqrt

from engine.frontier import State, normalize_leaf, prune_states


def pack_lines(options, width, height, gap, max_row=6):
    """Minimum-height ordered packing of the represented row frontiers.

    All leaves must be assigned exactly once. Row frontiers are capped, so this
    can abstain despite a feasible continuous arrangement. No shrinking occurs
    during packing. Return placements or None without changing the leaves.
    """
    n = len(options)
    if not n or any(not choices for choices in options):
        return None
    owned = set()
    for choices in options:
        indices = set(choices[0].placements)
        if not indices or any(set(s.placements)!=indices for s in choices):
            raise ValueError('Flow alternatives must represent the same nonempty leaf')
        if owned & indices:
            raise ValueError('Flow leaves repeat an element')
        owned.update(indices)
    best = [None] * (n+1)
    best[0] = (0., [])
    for start in range(n):
        if best[start] is None:
            continue
        frontier = [State(0, 0, 0, {})]
        for end in range(start, min(n, start+max_row)):
            merged = []
            for a in frontier:
                for b in options[end]:
                    x = a.width + (gap if end > start else 0)
                    if x+b.width > width or max(a.height, b.height) > height:
                        continue
                    placements = dict(a.placements)
                    placements.update({i:dict(e,x=e['x']+x) for i,e in b.placements.items()})
                    merged.append(State(x+b.width,max(a.height,b.height),0,placements))
            frontier = prune_states(merged,cap=16)
            if not frontier:
                break
            row = min(frontier,key=lambda s:(s.height,s.width))
            total = best[start][0] + (gap if start else 0) + row.height
            if total <= height and (best[end+1] is None or total < best[end+1][0]):
                best[end+1] = (total,best[start][1]+[row])
    if best[n] is None:
        return None
    total,rows = best[n]
    # Keep content together. Only a bounded share of slack becomes row spacing.
    rowgap = gap + min(gap, max(0,height-total)/max(1,len(rows)-1)) if len(rows)>1 else 0
    used = sum(row.height for row in rows)+rowgap*(len(rows)-1)
    y = (height-used)/2
    result = {}
    for row in rows:
        x = (width-row.width)/2
        result.update({i:dict(e,x=e['x']+x,y=e['y']+y) for i,e in row.placements.items()})
        y += row.height+rowgap
    return result


def _choices(source, unit, width, height, floor, base, scale, art_scale, measurer):
    elements = source['elements']
    texts = [i for i in unit.indices if elements[i]['type']=='text']
    shapes = [i for i in unit.indices if elements[i]['type']=='shape']
    # Reflow a supported stack before shrinking its source whitespace. Only a
    # single enclosing rectangular backing and disjoint ordered text blocks
    # establish this interpretation; ambiguous overlays keep rigid alternatives.
    if len(texts)>1 and len(shapes)==1 and len(unit.indices)==len(texts)+1:
        bi=shapes[0]; back=elements[bi]
        ordered=sorted(texts,key=lambda i:(elements[i]['y'],elements[i]['x']))
        supported=(back.get('shape_type')=='rectangle' and
                   not any(elements[i].get('rotation') for i in unit.indices) and
                   all(elements[i]['x']>=back['x'] and elements[i]['y']>=back['y'] and
                       elements[i]['x']+elements[i]['width']<=back['x']+back['width']+.01 and
                       elements[i]['y']+elements[i]['height']<=back['y']+back['height']+.01 and
                       (back.get('z_index',0),bi)<(elements[i].get('z_index',0),i) for i in texts) and
                   all(elements[a]['y']+elements[a]['height']<=elements[b]['y']+.01
                       for a,b in zip(ordered,ordered[1:])))
        if supported:
            states=[]
            pad=max(1,floor*.6); gap=max(1,floor*.5)
            for fraction in (1/5,1/3,1/2,2/3,1):
                outer=width*fraction; inner=outer-2*pad
                if inner<=0:continue
                edits={};y=pad
                for i in ordered:
                    old=elements[i]
                    size=max(1,int(min(old['font_size']*max(1,scale),floor*(old['font_size']/base)**.6)))
                    e=dict(old,x=pad,y=y,width=inner,font_size=float(size))
                    extent=measurer.measure(e);e['height']=max(1,extent.bottom+1)
                    if not extent.fits(inner,e['height']) or extent.missing_glyphs:break
                    edits[i]=e;y+=e['height']+gap
                if len(edits)==len(texts) and y-gap+pad<=height:
                    edits[bi]=dict(back,x=0.,y=0.,width=outer,height=y-gap+pad)
                    states.append(State(outer,y-gap+pad,0,edits))
            return prune_states(states,cap=12)
    simple = len(unit.indices)==1 and len(texts)==1
    pair = len(unit.indices)==2 and len(texts)==1 and len(shapes)==1
    if pair:
        text,back = elements[texts[0]],elements[shapes[0]]
        pair = (back.get('shape_type')=='rectangle' and
                text['x']>=back['x'] and text['y']>=back['y'] and
                text['x']+text['width']<=back['x']+back['width']+.01 and
                text['y']+text['height']<=back['y']+back['height']+.01)
    if (simple or pair) and not any(elements[i].get('rotation') for i in unit.indices):
        ti = texts[0]; text = elements[ti]
        size = max(1,int(min(text['font_size']*max(1,scale),floor*(text['font_size']/base)**.6)))
        padding = max(1,size*.4) if pair else 1
        widths = {width*f for f in (1/8,1/5,1/3,1/2,2/3,1)}
        widths.add(min(width,max(2,text['width']*scale+2*padding)))
        states = []
        for outer in sorted(widths):
            if outer<=2*padding:
                continue
            e = dict(text,x=padding,y=padding,width=outer-2*padding,font_size=float(size))
            extent = measurer.measure(e)
            h = max(1,extent.bottom+1)
            if not extent.fits(e['width'],h) or extent.missing_glyphs:
                continue
            e['height'] = h
            placements = {ti:e}
            if pair:
                placements[shapes[0]] = dict(elements[shapes[0]],x=0.,y=0.,width=outer,height=h+2*padding)
            # Explicit padding remains in the outer footprint even for plain text.
            if h+2*padding<=height:
                states.append(State(outer,h+2*padding,0,placements))
        return prune_states(states,cap=12)
    # Complex/rotated groups retain their internal geometry. Require every
    # member to meet the requested tier; do not hide tiny copy in a good mean.
    l,t,r,b = unit.bounds
    uw,uh = max(.001,r-l),max(.001,b-t)
    required = max((floor*(elements[i]['font_size']/base)**.6/elements[i]['font_size'] for i in texts),default=0)
    desired = max(required,scale*art_scale)
    s = min(width/uw,height/uh,desired)
    if s+1e-6 < required:
        return []
    edits = {}
    for i in unit.indices:
        old = elements[i]
        e = dict(old,x=(old['x']-l)*s,y=(old['y']-t)*s,width=max(.001,old['width']*s),height=max(.001,old['height']*s))
        if old['type']=='text':
            e,extent = measurer.fit(e,e['width'],e['height'],old['font_size']*s)
            if not extent.fits(e['width'],e['height']) or extent.missing_glyphs or e['font_size']+.01<floor:
                return []
        edits[i] = e
    return [normalize_leaf(edits)]


def flow_candidates(source,target,units,backgrounds,measurer):
    from engine.resize import materialize
    W,H = target['width'],target['height']
    text = [e for e in source['elements'] if e['type']=='text' and e['content'].strip()]
    if len(text)<3 or len(units)>64:
        return
    # A free decorative shape has no established reading-order position.
    # Packing it as content can displace an otherwise readable headline.
    # Backgrounds and supported/grouped shapes already have defined ownership.
    if any(len(u.indices)==1 and source['elements'][u.indices[0]]['type']=='shape' for u in units):
        return
    base = min(e['font_size'] for e in text)
    scale = sqrt(W*H/(source['canvas']['width']*source['canvas']['height']))
    margin = max(1,min(W,H)*.025)
    width,height = W-2*margin,H-2*margin
    if min(width,height)<=0:
        return
    for art_scale in (.5,.85):
        for floor in (24,20,16,14,12,10,8,7,6,5,4):
            options = [_choices(source,u,width,height,floor,base,scale,art_scale,measurer) for u in units]
            placed = pack_lines(options,width,height,margin)
            if placed is None:
                continue
            placed = {i:dict(e,x=e['x']+margin,y=e['y']+margin) for i,e in placed.items()}
            yield 'ordered-flow',materialize(source,target,placed,backgrounds)
            # Keep the first feasible sampled tier for each art allocation.
            # Other candidate families still supply hierarchy/spacing tradeoffs.
            break
