"""Source-preserving fitting and measured, bounded responsive group search."""
from copy import deepcopy
from dataclasses import dataclass
from math import log, sqrt, radians, cos, sin
from engine.measure import TextMeasurer
from engine.frontier import combine as combine_frontiers, normalize_leaf, prune_states
from engine.validation import validate_source, validate_target, validate_output, rotated_bounds
from engine.pixels import raster_diagnostics
from engine.composition import composition_metrics, optical_bounds

PIXEL_CONTRAST_WEIGHT = 2.
PIXEL_BUSYNESS_WEIGHT = .05


@dataclass
class Unit:
    indices: list[int]
    bounds: tuple


def union(elements):
    boxes = [rotated_bounds(e) for e in elements]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def background_indices(source):
    w, h = source['canvas']['width'], source['canvas']['height']
    result = []
    for i, e in enumerate(source['elements']):
        if e['type'] == 'text' or e.get('group_id') is not None or abs(e.get('rotation', 0)) > .001:
            continue
        if e['x'] <= 0 and e['y'] <= 0 and e['x']+e['width'] >= w and e['y']+e['height'] >= h:
            if e['type'] == 'shape' or e.get('fit') == 'cover':
                result.append(i)
    return result


def make_units(source, backgrounds, assets_dir=None):
    groups = {}
    elements = source['elements']
    # A backing and the content it supports are an inferred layout unit. Do
    # not write inferred group IDs or absorb any existing explicit group.
    parents = list(range(len(elements)))
    def root(i):
        while parents[i] != i:
            i = parents[i]
        return i
    for i,e in enumerate(elements):
        if i in backgrounds or e.get('group_id') is not None or e['type'] not in ('text','image'):
            continue
        box = optical_bounds(e,assets_dir) if e['type']=='image' else rotated_bounds(e)
        supports = []
        for j,b in enumerate(elements):
            if (j in backgrounds or b['type']!='shape' or b.get('group_id') is not None
                    or b.get('rotation') or b.get('shape_type')!='rectangle'
                    or (b.get('z_index',0),j)>=(e.get('z_index',0),i)):
                continue
            if (box[0]>=b['x'] and box[1]>=b['y'] and box[2]<=b['x']+b['width']
                    and box[3]<=b['y']+b['height'] and box[2]>box[0] and box[3]>box[1]):
                supports.append(j)
        if supports:
            backing = min(supports,key=lambda j:elements[j]['width']*elements[j]['height'])
            parents[root(i)] = root(backing)
    for i, e in enumerate(source['elements']):
        if i not in backgrounds:
            key = ('group', e['group_id']) if e.get('group_id') is not None else ('inferred', root(i))
            groups.setdefault(key, []).append(i)
    units = [Unit(v, union([source['elements'][i] for i in v])) for v in groups.values()]
    return sorted(units, key=lambda u: (u.bounds[1], u.bounds[0], u.indices[0]))


def translated(state, dx, dy):
    return {i: dict(p, x=p['x']+dx, y=p['y']+dy) for i, p in state.placements.items()}


def materialize(source, target, placements, backgrounds):
    elements = deepcopy(source['elements'])
    for i, edits in placements.items():
        elements[i].update({k: v for k, v in edits.items() if k in ('x','y','width','height','font_size')})
    for i in backgrounds:
        elements[i].update(x=0., y=0., width=float(target['width']), height=float(target['height']))
    return {'canvas': deepcopy(target), 'elements': elements}


def leaf_states(source, unit, target, measurer, scale):
    elements = source['elements']
    tw, th = target['width'], target['height']
    l,t,r,b = unit.bounds
    uw,uh = max(r-l,.001), max(b-t,.001)
    states = []
    if len(unit.indices) == 1 and elements[unit.indices[0]]['type'] == 'text':
        i = unit.indices[0]
        original = elements[i]
        preferred = max(1, original['font_size']*scale)
        sizes = sorted(set(max(1,int(min(original['font_size']*max(1.2,scale),preferred*f)))
                           for f in (.14,.22,.32,.45,.6,.75,.9,1,1.15,1.5,1.9,2.4)))
        widths = sorted(set(max(1.,min(tw,x)) for x in [original['width']*scale]
                            + [tw*f for f in (.12,.2,.3,.45,.65,.85,.96)]))
        for size in sizes:
            for width in widths:
                e = dict(original,x=0.,y=0.,width=width,font_size=float(size))
                ext = measurer.measure(e)
                if ext.right > width+.5 or ext.left < -.75 or ext.missing_glyphs:
                    continue
                e['height'] = max(1.,ext.bottom+1)
                state = normalize_leaf({i:e},utility=log(max(1,size)),rotations={i:e.get('rotation',0)})
                if state.width <= tw and state.height <= th:
                    states.append(state)
    else:
        max_scale = min(tw/uw,th/uh,scale*1.2)
        for fraction in (.12,.2,.3,.45,.6,.75,.9,1):
            s = max_scale*fraction
            edits,utility,valid = {},0.,True
            for i in unit.indices:
                original = elements[i]
                e = dict(original,x=(original['x']-l)*s,y=(original['y']-t)*s,
                         width=max(.001,original['width']*s),height=max(.001,original['height']*s))
                if e['type'] == 'text':
                    e,ext = measurer.fit(e,e['width'],e['height'],original['font_size']*s)
                    valid &= ext.fits(e['width'],e['height']) and not ext.missing_glyphs
                    utility += log(max(1,e['font_size']))
                elif e['type'] == 'image':
                    utility += .5*log(max(1,sqrt(e['width']*e['height'])))
                edits[i] = e
            if valid:
                states.append(normalize_leaf(edits,utility=utility,
                    rotations={i:elements[i].get('rotation',0) for i in edits}))
        # A contained label/background pair has a useful local responsive
        # interpretation: wrap the label and refit its existing backdrop.
        # Ambiguous or rotated groups keep the source-preserving alternatives.
        labels = [i for i in unit.indices if elements[i]['type']=='text']
        shapes = [i for i in unit.indices if elements[i]['type']=='shape']
        if len(labels)==1 and len(shapes)==1 and len(unit.indices)==2:
            ti,bi = labels[0],shapes[0]
            text,back = elements[ti],elements[bi]
            contained = (text['x']>=back['x'] and text['y']>=back['y'] and
                         text['x']+text['width']<=back['x']+back['width']+.01 and
                         text['y']+text['height']<=back['y']+back['height']+.01)
            if contained and not text.get('rotation') and not back.get('rotation'):
                for fraction in (.3,.5,.75,1,1.5,2):
                    size = max(1,int(text['font_size']*min(max(1.2,scale),scale*fraction)))
                    s = size/text['font_size']
                    px = max(1,(text['x']-back['x'])*s)
                    py = max(1,(text['y']-back['y'])*s*.6)
                    for width in (tw*.15,tw*.25,tw*.4,tw*.65):
                        if width<=2*px:continue
                        te = dict(text,x=px,y=py,width=max(1,width-2*px),font_size=float(size))
                        ext = measurer.measure(te)
                        te['height'] = max(1,ext.bottom+1)
                        if not ext.fits(te['width'],te['height']) or ext.missing_glyphs:continue
                        be = dict(back,x=0.,y=0.,width=width,height=te['height']+2*py)
                        state = normalize_leaf({ti:te,bi:be},utility=log(size))
                        if state.width<=tw and state.height<=th:states.append(state)
    return prune_states(states,cap=24)


def source_fit(source,target,units,backgrounds,measurer):
    sw,sh = source['canvas']['width'],source['canvas']['height']
    tw,th = target['width'],target['height']
    sx,sy = tw/sw,th/sh
    placements = {}
    for unit in units:
        l,t,r,b = unit.bounds
        s = min(sx,sy,tw/max(r-l,.001),th/max(b-t,.001))
        edits = {}
        for i in unit.indices:
            e = source['elements'][i]
            p = dict(e,x=(e['x']-l)*s,y=(e['y']-t)*s,width=max(.001,e['width']*s),height=max(.001,e['height']*s))
            if e['type'] == 'text':
                if len(unit.indices)==1 and not e.get('rotation'):
                    p['width'] = min(tw,max(p['width'],e['width']*sx))
                    p['height'] = min(th,max(p['height'],e['height']*sy))
                p,_ = measurer.fit(p,p['width'],p['height'],e['font_size']*sqrt(sx*sy))
            edits[i] = p
        state = normalize_leaf(edits,rotations={i:source['elements'][i].get('rotation',0) for i in edits})
        dx = max(0,min(tw-state.width,(l+r)/2*sx-state.width/2))
        dy = max(0,min(th-state.height,(t+b)/2*sy-state.height/2))
        placements.update(translated(state,dx,dy))
    return materialize(source,target,placements,backgrounds)


def overlap(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))


def ink_bounds(element,extent):
    angle = radians(element.get('rotation',0))
    cx,cy = element['width']/2,element['height']/2
    corners = [(element['x']+cx+(x-cx)*cos(angle)-(y-cy)*sin(angle),
                element['y']+cy+(x-cx)*sin(angle)+(y-cy)*cos(angle))
               for x in (extent.left,extent.right) for y in (extent.top,extent.bottom)]
    return min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)


def assess(source,output,backgrounds,measurer,assets_dir=None):
    elements = output['elements']
    ratios,sizes,image_ratios,boxes = [],[],[],[]
    overflow = missing = collision = drift = canvas_ink_overflow = 0.
    tw,th = output['canvas']['width'],output['canvas']['height']
    sw,sh = source['canvas']['width'],source['canvas']['height']
    for i,(src,e) in enumerate(zip(source['elements'],elements)):
        box = rotated_bounds(e)
        if e['type'] == 'text':
            ext = measurer.measure(e)
            overflow += max(0,ext.right-e['width'])+max(0,ext.bottom-e['height'])+max(0,-ext.left)+max(0,-ext.top)
            missing += ext.missing_glyphs
            ratios.append(log(e['font_size']/src['font_size']))
            sizes.append(e['font_size'])
            box = ink_bounds(e,ext)
            canvas_ink_overflow += max(0,-box[0])+max(0,-box[1])+max(0,box[2]-tw)+max(0,box[3]-th)
        elif e['type']=='image' and i not in backgrounds:
            image_ratios.append(log(max(.0001,sqrt(e['width']*e['height']/max(.0001,src['width']*src['height'])))))
            box = optical_bounds(e, assets_dir)
        boxes.append(box)
        if i not in backgrounds:
            drift += abs((e['x']+e['width']/2)/tw-(src['x']+src['width']/2)/sw)
            drift += abs((e['y']+e['height']/2)/th-(src['y']+src['height']/2)/sh)
    for i,a in enumerate(elements):
        if i in backgrounds:continue
        for j,b in enumerate(elements[:i]):
            if j in backgrounds or (a.get('group_id') is not None and a.get('group_id')==b.get('group_id')):continue
            if a['type']!='text' and b['type']!='text':continue
            area = overlap(boxes[i],boxes[j])
            denom = max(1,min((boxes[i][2]-boxes[i][0])*(boxes[i][3]-boxes[i][1]),
                              (boxes[j][2]-boxes[j][0])*(boxes[j][3]-boxes[j][1])))
            src_overlap = overlap(rotated_bounds(source['elements'][i]),rotated_bounds(source['elements'][j]))
            intentional = src_overlap>0 and a['type']!=b['type'] and (a['type']=='shape' or b['type']=='shape')
            # A preserved rectangular backing is not a content collision. This
            # also prevents reflow of a readable identity solely because its
            # text intentionally sits on an ungrouped contrast panel.
            if intentional:
                shape_index,text_index = (i,j) if a['type']=='shape' else (j,i)
                shape = elements[shape_index]
                src_shape = source['elements'][shape_index]
                src_text_box = rotated_bounds(source['elements'][text_index])
                def contains(outer,inner):
                    return outer[0]<=inner[0] and outer[1]<=inner[1] and outer[2]>=inner[2] and outer[3]>=inner[3]
                if (shape.get('shape_type')=='rectangle' and not shape.get('rotation')
                        and (shape.get('z_index',0),shape_index)<(elements[text_index].get('z_index',0),text_index)
                        and contains(rotated_bounds(src_shape),src_text_box)
                        and contains(boxes[shape_index],boxes[text_index])):
                    continue
            collision += area/denom*(.15 if intentional else 1)
    mean = sum(ratios)/max(1,len(ratios))
    hierarchy = sum(abs(v-mean) for v in ratios)/max(1,len(ratios))
    source_sizes = [e['font_size'] for e in source['elements'] if e['type']=='text']
    inversions = [max(0,log(sizes[j]/sizes[i])) for i in range(len(sizes)) for j in range(len(sizes))
                  if source_sizes[i]>source_sizes[j]*1.25]
    inversion = sum(inversions)/max(1,len(inversions))
    score = mean+.25*sum(image_ratios)/max(1,len(image_ratios))-.22*hierarchy-.7*inversion-.16*drift/max(1,len(elements))-3*collision-10*overflow-100*missing-100*canvas_ink_overflow
    return dict(score=score,text_overflow_px=overflow,missing_glyphs=missing,collision_proxy=collision,
                hierarchy_deviation=hierarchy,minimum_font_size=min(sizes,default=None),mean_log_font_scale=mean,
                canvas_ink_overflow_px=canvas_ink_overflow,hierarchy_inversion=inversion)


def responsive_candidates(source,target,units,backgrounds,measurer):
    tw,th = target['width'],target['height']
    scale = sqrt(tw*th/(source['canvas']['width']*source['canvas']['height']))
    options = [leaf_states(source,u,target,measurer,scale) for u in units]
    if not options or any(not x for x in options):return
    margin = gap = min(tw,th)*.025
    def combine(children,**kwargs):
        return combine_frontiers(children,max_width=tw-2*margin,max_height=th-2*margin,**kwargs)
    orders = [list(range(len(units)))]
    horizontal = sorted(range(len(units)),key=lambda j:(units[j].bounds[0],units[j].bounds[1]))
    if horizontal != orders[0]:orders.append(horizontal)
    def emit(states,name):
        for state in states:
            if state.width <= tw-2*margin and state.height <= th-2*margin:
                yield name,materialize(source,target,translated(state,(tw-state.width)/2,(th-state.height)/2),backgrounds)
    for order in orders:
        leaves = [options[j] for j in order]
        for direction in ('row','column'):
            yield from emit(combine(leaves,direction=direction,gap=gap,align='center',cap=40),'responsive-'+direction)
            other = 'column' if direction=='row' else 'row'
            for cut in sorted(set([len(leaves)//2,1,len(leaves)-1])):
                if cut<=0 or cut>=len(leaves):continue
                a = combine(leaves[:cut],direction=other,gap=gap,align='center',cap=24)
                b = combine(leaves[cut:],direction=other,gap=gap,align='center',cap=24)
                yield from emit(combine([a,b],direction=direction,gap=gap*2,align='center',cap=40),'responsive-panels')
    # A common source-derived explanation is continuous copy, flanked by
    # imagery/action groups, with small bottom copy spanning the composition.
    # It is an alternative hypothesis, never a hard semantic label or ID rule.
    text_units = [j for j,u in enumerate(units) if len(u.indices)==1 and source['elements'][u.indices[0]]['type']=='text']
    if text_units:
        largest = max(source['elements'][units[j].indices[0]]['font_size'] for j in text_units)
        footers = [j for j in text_units if units[j].bounds[1]>.8*source['canvas']['height']
                   and source['elements'][units[j].indices[0]]['font_size']<largest*.55]
        copy_units = [j for j in text_units if j not in footers]
        extras = [j for j in range(len(units)) if j not in text_units]
        if copy_units and extras:
            copy_states = combine([options[j] for j in copy_units],direction='column',gap=gap,align='center',cap=32)
            for cut in sorted(set([1,len(extras)//2,len(extras)])):
                panels = []
                if extras[:cut]:panels.append(combine([options[j] for j in extras[:cut]],direction='column',gap=gap,align='center',cap=24))
                panels.append(copy_states)
                if extras[cut:]:panels.append(combine([options[j] for j in extras[cut:]],direction='column',gap=gap,align='center',cap=24))
                body = combine(panels,direction='row',gap=gap*2,align='center',cap=40)
                if footers:
                    footer = combine([options[j] for j in footers],direction='column',gap=gap,align='center',cap=24)
                    body = combine([body,footer],direction='column',gap=gap,align='center',cap=40)
                yield from emit(body,'responsive-copy-panels')


def evaluate_candidate(source,design,backgrounds,measurer,assets_dir=None):
    """Separate safety and composition terms; also used by pool ablations."""
    quality = assess(source,design,backgrounds,measurer,assets_dir)
    composition = composition_metrics(source,design,measurer,assets_dir)
    # Font inflation cannot buy its way past a tiny subject or reversed hierarchy.
    score = (composition['score'] - 3*quality['collision_proxy']
             -10*quality['text_overflow_px'] -100*quality['missing_glyphs']
             -100*quality['canvas_ink_overflow_px'])
    return score,dict(quality,composition=composition)


def resize_with_diagnostics(source,target_canvas,fonts_dir=None,assets_dir=None):
    problems = validate_source(source)+validate_target(target_canvas)
    if problems:raise ValueError('; '.join(problems))
    measurer = TextMeasurer(fonts_dir)
    backgrounds = background_indices(source)
    units = make_units(source,backgrounds,assets_dir)
    if source['canvas']==target_canvas and not validate_output(source,target_canvas,source):
        quality = assess(source,source,backgrounds,measurer,assets_dir)
        if quality['text_overflow_px']<=.75 and quality['canvas_ink_overflow_px']<=.01 and quality['collision_proxy']<.01 and not quality['missing_glyphs']:
            return deepcopy(source),dict(quality,method='identity',candidates=1)
    candidates = [('source-fit',source_fit(source,target_canvas,units,backgrounds,measurer))]
    candidates.extend(responsive_candidates(source,target_canvas,units,backgrounds,measurer) or [])
    from engine.editorial import editorial_candidates
    candidates.extend(editorial_candidates(source,target_canvas,measurer,assets_dir) or [])
    from engine.series import series_candidates
    candidates.extend(series_candidates(source,target_canvas,measurer,assets_dir) or [])
    valid = []
    for method,design in candidates:
        if not validate_output(source,target_canvas,design):
            score,quality = evaluate_candidate(source,design,backgrounds,measurer,assets_dir)
            valid.append((score,method,design,quality))
    if not valid:raise ValueError('No candidate satisfies independent output validation')
    # Rerank a bounded shortlist using actual unchanged imagery. This is a
    # weak signal: average contrast cannot recognize subjects or certify text.
    shortlist = sorted(valid,key=lambda c:c[0],reverse=True)[:5]
    incumbent = next((c for c in valid if c[1]=='source-fit'),None)
    if incumbent is not None and all(c is not incumbent for c in shortlist):
        shortlist.append(incumbent)
    ranked = []
    for proxy,method,design,quality in shortlist:
        raster = raster_diagnostics(design,fonts_dir,assets_dir)
        score = proxy-PIXEL_CONTRAST_WEIGHT*raster['low_contrast_proxy']-PIXEL_BUSYNESS_WEIGHT*raster['busyness_proxy']
        ranked.append((score,method,design,dict(quality,raster=raster,selection_score=score)))
    best = max(ranked,key=lambda c:c[0])
    # Repair a demonstrated layout weakness, not an already-readable source
    # relationship. Keep the fully raster-ranked incumbent in competition so
    # a new proposal cannot evict it merely by entering the proxy shortlist.
    q = best[3]
    needs_repair = ((q['minimum_font_size'] is not None and q['minimum_font_size']<12)
                    or q['text_overflow_px']>.75 or q['canvas_ink_overflow_px']>.01
                    or q['collision_proxy']>.05)
    if needs_repair:
        from engine.flow import flow_candidates, image_floors, retains_images
        # Freeze asset floors against the pre-repair incumbent. Do not ratchet
        # them against whichever proposal happened to be visited last.
        floors = image_floors(best[2],assets_dir)
        repairs = list(flow_candidates(source,target_canvas,units,backgrounds,measurer,
                                       floors,assets_dir) or [])
        from engine.series import grid_candidates
        repairs.extend(grid_candidates(source,target_canvas,measurer,assets_dir) or [])
        candidates.extend(repairs)
        for method,design in repairs:
            if validate_output(source,target_canvas,design) or not retains_images(design,floors,assets_dir):
                continue
            proxy,quality = evaluate_candidate(source,design,backgrounds,measurer,assets_dir)
            valid.append((proxy,method,design,quality))
            # Restoring full image bounds can move optical support into a
            # neighbor. Do not trade a new collision for a better scalar score.
            if quality['collision_proxy'] > max(.01,q['collision_proxy']):
                continue
            raster = raster_diagnostics(design,fonts_dir,assets_dir)
            score = proxy-PIXEL_CONTRAST_WEIGHT*raster['low_contrast_proxy']-PIXEL_BUSYNESS_WEIGHT*raster['busyness_proxy']
            if score > best[0]:
                best = (score,method,design,dict(quality,raster=raster,selection_score=score))
    return best[2],dict(best[3],method=best[1],candidates=len(candidates),valid_candidates=len(valid),
        approximate_frontier=True,quality_warning=best[3]['text_overflow_px']>.75 or best[3]['canvas_ink_overflow_px']>.01 or bool(best[3]['missing_glyphs']) or
        best[3]['raster']['low_contrast_proxy']>.05 or
        (best[3]['minimum_font_size'] is not None and best[3]['minimum_font_size']<8))


def resize(source,target_canvas):
    return resize_with_diagnostics(source,target_canvas)[0]
