"""Editorial composition proposals from geometry, typography and visible assets.

No sample IDs, copy keywords, asset replacement or style edits. Explicit groups
remain coherent. Optical image fitting reads alpha only; full image rectangles
remain in bounds and retain their source aspect ratio. These are candidates,
not a claim that every dense target can be legible.
"""
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from math import sqrt, radians, sin, cos
from pathlib import Path

from PIL import Image
from engine.validation import rotated_bounds
from engine.frontier import scaled_dimensions


@dataclass
class Unit:
    indices: list
    bounds: tuple
    text: list
    shapes: list
    images: list


def _bounds(elements):
    boxes = [rotated_bounds(e) for e in elements]
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


@lru_cache(maxsize=256)
def _asset_alpha(path, modified):
    try:
        with Image.open(path) as image:
            alpha = image.convert('RGBA').getchannel('A')
            box = alpha.getbbox()
            if box:
                return image.size, box
    except (OSError, ValueError):
        pass
    return None


def visible_fraction(element, assets_dir):
    """Visible rectangle fractions in the unchanged contain image box."""
    if element['width']<=0 or element['height']<=0 or element.get('fit', 'contain') != 'contain':
        return (0., 0., 1., 1.)
    path = Path(assets_dir) / str(element.get('asset_id', ''))
    # Asset lookup is analysis only; missing assets retain the official placeholder.
    try:
        item = _asset_alpha(str(path), path.stat().st_mtime_ns)
    except OSError:
        item = None
    if item is None:
        return (0., 0., 1., 1.)
    (iw, ih), (l,t,r,b) = item
    bw, bh = element['width'], element['height']
    scale = min(bw/iw, bh/ih)
    px, py = (bw-iw*scale)/2, (bh-ih*scale)/2
    return ((px+l*scale)/bw, (py+t*scale)/bh, (px+r*scale)/bw, (py+b*scale)/bh)


def _classify(source, assets_dir):
    elements = source['elements']; sw,sh = source['canvas']['width'],source['canvas']['height']
    backgrounds=[]; decorations=[]; grouped={}
    for i,e in enumerate(elements):
        full = e['x'] <= 0 and e['y'] <= 0 and e['x']+e['width'] >= sw and e['y']+e['height'] >= sh
        if full and e.get('group_id') is None and not e.get('rotation') and (e['type']=='shape' or e.get('fit')=='cover'):
            backgrounds.append(i)
        elif e['type']=='shape' and e.get('group_id') is None:
            decorations.append(i)
        else:
            key=('g',e['group_id']) if e.get('group_id') is not None else ('i',i)
            grouped.setdefault(key,[]).append(i)
    units=[]
    for indices in grouped.values():
        units.append(Unit(indices,_bounds([elements[i] for i in indices]),
                          [i for i in indices if elements[i]['type']=='text'],
                          [i for i in indices if elements[i]['type']=='shape'],
                          [i for i in indices if elements[i]['type']=='image']))
    # Largest visible image is hero. Wide, upper source images are brand marks.
    image_units=[u for u in units if len(u.indices)==1 and u.images]
    def visible_area(u):
        e=elements[u.indices[0]]; l,t,r,b=visible_fraction(e,assets_dir)
        return e['width']*e['height']*(r-l)*(b-t)
    logos=[u for u in image_units if u.bounds[1] < sh*.3 and
           elements[u.indices[0]]['width']/max(1,elements[u.indices[0]]['height']) > 1.7]
    logo=min(logos,key=lambda u:u.bounds[1],default=None)
    hero=max([u for u in image_units if u is not logo],key=visible_area,default=None)
    # Tiny peripheral image with no other hero is not promoted to dominant art.
    if hero and visible_area(hero) < sw*sh*.015:
        hero=None
    plain=[u for u in units if len(u.indices)==1 and u.text]
    headline=max(plain,key=lambda u:elements[u.text[0]].get('font_size',1),default=None)
    legal=[u for u in plain if u is not headline and u.bounds[1] > sh*.82 and
           elements[u.text[0]]['font_size'] <= (elements[headline.text[0]]['font_size']*.4 if headline else 0)]
    body=sorted([u for u in plain if u is not headline and u not in legal],key=lambda u:(u.bounds[1],u.bounds[0]))
    labels=[u for u in units if u.text and u.shapes]
    actions=[u for u in labels if (u.bounds[1]+u.bounds[3])/2 > sh*.58]
    action=max(actions,key=lambda u:max(elements[i]['font_size'] for i in u.text),default=None)
    badges=sorted([u for u in labels if u is not action],key=lambda u:(u.bounds[1],u.bounds[0]))
    used=[u for u in [logo,hero,headline,action]+body+legal+badges if u is not None]
    extras=[u for u in units if all(u is not v for v in used)]
    return backgrounds,decorations,logo,hero,headline,body,legal,badges,action,extras


def _image(output, index, slot, assets_dir, target):
    """Fit optical support to slot while keeping the full image box in canvas."""
    e=output[index]; x,y,w,h=slot; W,H=target['width'],target['height']
    l,t,r,b=visible_fraction(e,assets_dir)
    bw,bh=e['width'],e['height']
    scale=min(w/max(.001,bw*(r-l)),h/max(.001,bh*(b-t)),W/bw,H/bh)
    nw,nh=bw*scale,bh*scale
    ox=x+(w-nw*(r-l))/2-nw*l; oy=y+(h-nh*(b-t))/2-nh*t
    e.update(x=max(0.,min(W-nw,ox)),y=max(0.,min(H-nh,oy)),width=nw,height=nh)


def _text(output,index,slot,preferred,measurer):
    x,y,w,h=slot; e=output[index]
    trial,extent=measurer.fit(e,max(1,w),max(1,h),max(1,preferred))
    # fit() permits subpixel tolerance, but the layout must reserve actual ink
    # plus breathing room; clipping this to the proposed slot hides a spill.
    actual_h=max(1,extent.bottom+1)
    e.update(x=x,y=y,width=max(1,w),height=max(1,actual_h),font_size=trial['font_size'])
    return actual_h


def _unit(output,unit,slot,preferred,measurer,target):
    x,y,w,h=slot
    if len(unit.text)==1 and len(unit.shapes)==1 and len(unit.indices)==2 and not any(output[i].get('rotation') for i in unit.indices):
        ti,bi=unit.text[0],unit.shapes[0]
        padding=max(1,min(h*.2,preferred*.55))
        te,extent=measurer.fit(output[ti],max(1,w-2*padding),max(1,h-2*padding),max(1,preferred))
        size=te['font_size']; labelheight=max(1,extent.bottom+1)
        # Tighten one-line labels; preserve existing alignment/style.
        natural=max(1,extent.right-extent.left)+2*padding+2
        width=min(w,max(natural,min(w,h*2)))
        te,extent=measurer.fit(output[ti],max(1,width-2*padding),max(1,h-2*padding),size)
        height=min(h,max(extent.bottom+2*padding+1,size*1.8))
        output[bi].update(x=x+(w-width)/2,y=y,width=width,height=height)
        output[ti].update(x=x+(w-width)/2+padding,y=y+(height-extent.bottom)/2,
                          width=max(1,width-2*padding),height=max(1,extent.bottom+1),font_size=te['font_size'])
        return height
    # A rotated single-label lockup may reflow internally while retaining both
    # original rotations. Solve its actual rotated footprint, not its old width.
    if len(unit.text)==1 and len(unit.shapes)==1 and len(unit.indices)==2:
        ti,bi=unit.text[0],unit.shapes[0]
        if abs(output[ti].get('rotation',0)-output[bi].get('rotation',0)) < .001:
            angle=radians(output[bi].get('rotation',0)); c,ss=abs(cos(angle)),abs(sin(angle))
            for size in range(max(1,int(preferred)),0,-1):
                shape_h=size*2.1
                shape_w=min((w-shape_h*ss)/max(c,.001),
                            (h-shape_h*c)/max(ss,.001) if ss else w)
                if shape_w <= size*2:continue
                pad=max(1,size*.55)
                te=dict(output[ti],width=max(1,shape_w-2*pad),font_size=float(size))
                extent=measurer.measure(te)
                if extent.right>te['width']+.5 or extent.bottom>shape_h-2:continue
                # Center ink geometrically in its own rotated text box.
                outer_w=shape_w*c+shape_h*ss; outer_h=shape_w*ss+shape_h*c
                centerx=x+w/2; centery=y+h/2
                output[bi].update(x=centerx-shape_w/2,y=centery-shape_h/2,width=shape_w,height=shape_h)
                text_h=max(1,extent.bottom+1)
                output[ti].update(x=centerx-te['width']/2,y=centery-text_h/2,
                                  width=te['width'],height=text_h,font_size=float(size))
                return outer_h
    # Preserve internal rotated/complex lockup geometry as a coherent unit.
    l,t,r,b=_bounds([output[i] for i in unit.indices]); s=min(w/max(1,r-l),h/max(1,b-t))
    edits=[]
    for i in unit.indices:
        e=output[i]
        width, height = scaled_dimensions(e, s)
        p=dict(e,x=(e['x']-l)*s,y=(e['y']-t)*s,width=width,height=height)
        if p['type']=='text':
            p,_=measurer.fit(p,p['width'],p['height'],min(preferred,e['font_size']*s))
        edits.append((i,p))
    l,t,r,b=_bounds([p for i,p in edits]); dx=x+(w-(r-l))/2-l; dy=y+(h-(b-t))/2-t
    for i,p in edits:
        output[i].update({k:p[k] for k in ('width','height')})
        output[i].update(x=p['x']+dx,y=p['y']+dy)
        if p['type']=='text':output[i]['font_size']=p['font_size']
    return b-t


def _badge_row(output,badges,slot,preferred,measurer,target):
    if not badges:return 0
    x,y,w,h=slot; gap=min(h*.18,w*.015)
    widths=[max(1,u.bounds[2]-u.bounds[0]) for u in badges]; total=sum(widths)
    remaining=w-gap*(len(badges)-1); height=0
    for u,weight in zip(badges,widths):
        width=remaining*weight/total
        height=max(height,_unit(output,u,(x,y,width,h),preferred,measurer,target)); x+=width+gap
    return height


def editorial_candidates(source,target,measurer,assets_dir=None):
    """Yield independent hero/copy/action compositions, preserving every element."""
    assets_dir=Path(assets_dir or Path(__file__).resolve().parents[1]/'brand_kit/assets')
    W,H=target['width'],target['height']; sw,sh=source['canvas']['width'],source['canvas']['height']
    if min(W,H,sw,sh)<=0:return
    if any(e['type']=='image' and (min(e['width'],e['height'])<=0 or e.get('rotation')) for e in source['elements']):return
    roles=_classify(source,assets_dir)
    backgrounds,deco,logo,hero,headline,body,legal,badges,action,extras=roles
    if headline is None:return
    if len(legal)>1:return  # This template has one footer slot; never overlay disclaimers.
    # This grammar understands single hero art and simple label lockups. A
    # product card or multiline support panel is NOT an auxiliary footer mark.
    # Abstain rather than crush unsupported compounds into tiny thumbnails.
    if any(len(u.indices)>1 for u in extras):return
    if any(len(u.indices)!=2 or len(u.text)!=1 or len(u.shapes)!=1 for u in badges+([action] if action else [])):return
    if len(extras)>3:return
    for i in deco:
        shape=source['elements'][i]
        if shape.get('shape_type')!='rectangle':continue
        for text in source['elements']:
            if text['type']!='text' or text.get('group_id') is not None:continue
            if shape.get('z_index',0)>text.get('z_index',0):continue
            overlap=max(0,min(shape['x']+shape['width'],text['x']+text['width'])-max(shape['x'],text['x']))*max(0,min(shape['y']+shape['height'],text['y']+text['height'])-max(shape['y'],text['y']))
            if overlap > .85*text['width']*text['height']:
                return  # Unspecified support association needs a compound grammar.
    if any(u.images and source['elements'][u.images[0]]['width']*source['elements'][u.images[0]]['height'] > sw*sh*.03
           and (assets_dir/source['elements'][u.images[0]].get('asset_id','')).is_file() for u in extras):return
    dense=W/H>=4 and sum(e['type']=='text' for e in source['elements'])>=5
    orientations=['dense'] if dense else (['wide-left','wide-right'] if W/H>=1.7 and hero else ['poster'])
    for mode in orientations:
        out=deepcopy(source['elements']); margin=max(2,min(W,H)*(.035 if dense else .045)); gap=max(2,min(W,H)*.025)
        for i in backgrounds:out[i].update(x=0.,y=0.,width=float(W),height=float(H))
        # Decorations stay attached to source-relative edges, never consume a content cell.
        for i in deco:
            e=out[i]; s=min(sqrt(W*H/(sw*sh)),min(W,H)*.65/max(e['width'],e['height'],1))
            nw,nh=e['width']*s,e['height']*s
            e.update(x=max(0,min(W-nw,(e['x']+e['width']/2)/sw*W-nw/2)),
                     y=max(0,min(H-nh,(e['y']+e['height']/2)/sh*H-nh/2)),width=nw,height=nh)
        if mode=='dense':
            footer=max(9,H*.13) if legal else 0; usable=H-footer-2*margin
            rail=W*.195; art=W*.17 if hero or logo else 0; cx=art+margin; cw=W-art-rail-3*margin
            rotated_badges=[u for u in badges if any(out[i].get('rotation') for i in u.indices)]
            rail_badges=[u for u in badges if u not in rotated_badges]
            if hero:
                _image(out,hero.indices[0],(art*.56,margin,art*.42,H-2*margin),assets_dir,target)
            if logo:_image(out,logo.indices[0],(margin,margin,art*(.46 if hero else .9),usable*.37),assets_dir,target)
            for j,u in enumerate(rotated_badges):
                _unit(out,u,(margin,usable*.57+j*usable*.38/max(1,len(rotated_badges)),art*.53,usable*.38/max(1,len(rotated_badges))),H*.09,measurer,target)
            head_h=_text(out,headline.text[0],(cx,margin,cw,usable*.65),H*.22,measurer)
            by=margin+head_h+max(1,gap*.35)
            for u in body:
                available=max(1,(H-footer-margin-by)/max(1,len(body)))
                used=_text(out,u.text[0],(cx,by,cw,available),max(7,H*.105),measurer); by+=used+1
            rx=W-rail-margin; ry=margin
            groups=rail_badges+([action] if action else [])
            heights=[1.45 if u is action else 1 for u in groups]; unit_h=(usable-gap*.25*max(0,len(groups)-1))/max(1,sum(heights))
            for u,weight in zip(groups,heights):
                _unit(out,u,(rx,ry,rail,unit_h*weight),min(H*.105,out[headline.text[0]]['font_size']*.8),measurer,target)
                ry+=unit_h*weight+gap*.25
            for u in legal:_text(out,u.text[0],(margin,H-footer,W-2*margin-(36 if extras else 0),footer),max(5,H*.085),measurer)
            ex=W-margin
            for u in extras:
                ew=min(32,W*.06);eh=min(footer or H*.15,H*.15)
                if len(u.images)==1 and len(u.indices)==1:_image(out,u.indices[0],(ex-ew,H-eh,ew,eh),assets_dir,target)
                else:_unit(out,u,(ex-ew,H-eh,ew,eh),max(1,H*.06),measurer,target)
                ex-=ew+2
        elif mode.startswith('wide'):
            artw=W*.31; copyw=W*.61; cx=W*.35 if mode=='wide-left' else W*.04
            ax=W*.02 if mode=='wide-left' else W*.67
            if hero:_image(out,hero.indices[0],(ax,margin,artw,H-2*margin),assets_dir,target)
            y=margin
            if logo:
                _image(out,logo.indices[0],(cx+copyw*.29,y,copyw*.42,H*.14),assets_dir,target); y+=H*.18
            if badges:_badge_row(out,badges,(ax,margin,artw,H*.09),H*.045,measurer,target)
            hh=_text(out,headline.text[0],(cx,y,copyw,H*.24),H*.18,measurer); y+=hh+gap
            for u in body:
                used=_text(out,u.text[0],(cx,y,copyw,H*.16/max(1,len(body))),H*.073,measurer);y+=used+gap*.8
            if action:
                used=_unit(out,action,(cx+copyw*.24,y,copyw*.52,min(H*.15,H-margin-y)),H*.065,measurer,target); y+=used+gap
            footer_y=H-margin-max(10,H*.045)
            for u in legal:_text(out,u.text[0],(cx,footer_y,copyw,H*.05),H*.033,measurer)
            for j,u in enumerate(extras):
                slot=(W-margin-W*.07*(j+1),H-margin-H*.12,W*.065,H*.12)
                if len(u.images)==1 and len(u.indices)==1:_image(out,u.indices[0],slot,assets_dir,target)
                else:_unit(out,u,slot,H*.035,measurer,target)
        else:
            copyw=W*.86; cx=(W-copyw)/2
            # Measure the narrative stack first; give its remaining area to hero.
            headpref=W*.064; bodypref=W*.027
            hh=_text(out,headline.text[0],(cx,0,copyw,H*.21),headpref,measurer)
            body_h=[]
            for u in body:body_h.append(_text(out,u.text[0],(cx,0,copyw,H*.13/max(1,len(body))),bodypref,measurer))
            badge_h=min(H*.05,W*.06) if badges else 0
            action_h=min(H*.065,W*.095) if action else 0
            legal_h=max(12,H*.035) if legal else 0
            stack=hh+sum(body_h)+gap*(1+len(body)+bool(badges)+bool(action))+badge_h+action_h
            bottom=H-margin-legal_h-(gap if legal else 0)
            copy_y=max(H*.37,bottom-stack) if hero else max(H*.35,(H-stack)/2)
            if copy_y+stack>bottom:copy_y=bottom-stack
            logo_h=min(H*.09,W*.13) if logo else 0
            if logo:_image(out,logo.indices[0],(W*.3,margin,W*.4,logo_h),assets_dir,target)
            hero_top=margin+logo_h+gap
            if hero:_image(out,hero.indices[0],(W*.16,hero_top,W*.68,max(1,copy_y-hero_top-gap*1.6)),assets_dir,target)
            y=copy_y
            out[headline.text[0]]['y']=y;y+=hh+gap
            for u,height in zip(body,body_h):out[u.text[0]]['y']=y;y+=height+gap
            if badges:
                _badge_row(out,badges,(cx,y,copyw,badge_h),W*.019,measurer,target);y+=badge_h+gap
            if action:_unit(out,action,(W*.24,y,W*.52,action_h),W*.027,measurer,target)
            for u in legal:_text(out,u.text[0],(cx,H-margin-legal_h,copyw-(W*.11*len(extras)),legal_h),W*.013,measurer)
            for j,u in enumerate(extras):
                slot=(W-margin-W*.1*(j+1),H-margin-H*.04,W*.09,H*.035)
                if len(u.images)==1 and len(u.indices)==1:_image(out,u.indices[0],slot,assets_dir,target)
                else:_unit(out,u,slot,W*.015,measurer,target)
        # Source-relative decorative supports follow the hero instead of
        # drifting into a disconnected cell. Keep size/style/rotation intact
        # except the same uniform geometric scale as their supported image.
        if hero:
            hi=hero.indices[0]; oldhero=source['elements'][hi]; newhero=out[hi]
            for i in deco:
                original=source['elements'][i]
                if original.get('z_index',0)>oldhero.get('z_index',0):continue
                hx=oldhero['x']+oldhero['width']/2; hy=oldhero['y']+oldhero['height']/2
                if not (original['x']<=hx<=original['x']+original['width'] and original['y']<=hy<=original['y']+original['height']):continue
                scale=min(newhero['width']/oldhero['width'],newhero['height']/oldhero['height'])
                shape=out[i]; shape.update(width=original['width']*scale,height=original['height']*scale,
                    x=newhero['x']+(original['x']-oldhero['x'])*scale,y=newhero['y']+(original['y']-oldhero['y'])*scale)
                l,t,r,b=rotated_bounds(shape)
                if r-l>W or b-t>H:
                    shrink=min(W/(r-l),H/(b-t));shape['width']*=shrink;shape['height']*=shrink
                    l,t,r,b=rotated_bounds(shape)
                shape['x']+=max(0,-l)-max(0,r-W);shape['y']+=max(0,-t)-max(0,b-H)
        yield 'editorial-'+mode,dict(canvas=deepcopy(target),elements=out)
