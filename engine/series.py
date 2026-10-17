"""Repeated-card editorial layouts; preserve source series and footer order.

This candidate grammar accepts explicit, structurally similar image/text cards.
Unsupported surrounding elements cause abstention, not silently tiny extras.
Only geometry/font-size fields change. Alpha is measured, never edited.
"""
from copy import deepcopy
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

from engine.editorial import visible_fraction


@dataclass
class Card:
    backdrop: int
    image: int
    texts: list


def _groups(source):
    elements=source['elements']; groups={}
    for i,e in enumerate(elements):
        if e.get('group_id') is not None:groups.setdefault(e['group_id'],[]).append(i)
    cards=[]; actions=[]
    for indices in groups.values():
        if any(elements[i].get('rotation') for i in indices):return None
        shapes=[i for i in indices if elements[i]['type']=='shape']
        images=[i for i in indices if elements[i]['type']=='image']
        texts=[i for i in indices if elements[i]['type']=='text']
        if len(shapes)!=1 or elements[shapes[0]].get('shape_type')!='rectangle':return None
        if len(images)==1 and len(texts)>=2:
            card=elements[shapes[0]]
            if card['width']<=0 or card['height']<=0 or min(elements[images[0]]['width'],elements[images[0]]['height'])<=0:return None
            # Backdrop is a real support, not an unrelated rectangle sharing a tag.
            if any(elements[i]['x']<card['x']-.01 or elements[i]['y']<card['y']-.01 or
                   elements[i]['x']+elements[i]['width']>card['x']+card['width']+.01 or
                   elements[i]['y']+elements[i]['height']>card['y']+card['height']+.01
                   for i in images+texts):return None
            cards.append(Card(shapes[0],images[0],sorted(texts,key=lambda i:(elements[i]['y'],elements[i]['x']))))
        elif not images and len(texts)==1:actions.append((shapes[0],texts[0]))
        else:return None
    if len(cards)<2:return None
    widths=[elements[c.backdrop]['width'] for c in cards]; heights=[elements[c.backdrop]['height'] for c in cards]
    if max(widths)/min(widths)>1.6 or max(heights)/min(heights)>1.6:return None
    # Existing source rows first, then left-to-right within each row.
    pending=sorted(cards,key=lambda c:(elements[c.backdrop]['y'],elements[c.backdrop]['x']))
    ordered=[]
    while pending:
        y=elements[pending[0].backdrop]['y']; tolerance=min(heights)*.2
        row=[c for c in pending if elements[c.backdrop]['y']<=y+tolerance]
        ordered.extend(sorted(row,key=lambda c:elements[c.backdrop]['x']))
        pending=[c for c in pending if c not in row]
    return ordered,actions


def _text_plan(source,indices,width,preferred_scale,measurer,gap,factor=1):
    plan=[]; total=0
    for i in indices:
        e=source['elements'][i];size=max(1,int(e['font_size']*preferred_scale*factor))
        trial=dict(e,width=width,font_size=float(size));extent=measurer.measure(trial)
        height=max(1,extent.bottom+1)
        if not extent.fits(width,height) or extent.missing_glyphs:return None
        plan.append((i,size,height));total+=height
    return plan,total+gap*max(0,len(plan)-1)


def _fit_stack(source,indices,width,height,scale,measurer,gap):
    for step in range(101):
        result=_text_plan(source,indices,width,scale,measurer,gap,max(.01,1-step*.01))
        if result and result[1]<=height:return result
    return None


def _place_stack(out,plan,x,y,width,gap):
    for i,size,height in plan:
        out[i].update(x=x,y=y,width=width,height=height,font_size=float(size));y+=height+gap


def _art(out,index,slot,target,assets_dir):
    e=out[index];x,y,w,h=slot;W,H=target['width'],target['height']
    l,t,r,b=visible_fraction(e,assets_dir);bw,bh=e['width'],e['height']
    centerx,centery=x+w/2,y+h/2
    mx,my=(l+r)/2,(t+b)/2
    # Clamping an oversized full box after optical placement shifts opaque art
    # into neighboring copy. Bound scale so the optical center is achievable
    # with the full unchanged image box inside the canvas in the first place.
    scale=min(w/max(.001,bw*(r-l)),h/max(.001,bh*(b-t)),W/bw,H/bh,
              centerx/max(.001,bw*mx),(W-centerx)/max(.001,bw*(1-mx)),
              centery/max(.001,bh*my),(H-centery)/max(.001,bh*(1-my)))
    nw,nh=bw*scale,bh*scale
    e.update(x=max(0,centerx-nw*mx),y=max(0,centery-nh*my),width=nw,height=nh)


def series_candidates(source,target,measurer,assets_dir=None):
    """Yield consistent vertical-row or horizontal-column card compositions."""
    classified=_groups(source)
    if classified is None:return
    cards,actions=classified;elements=source['elements'];W,H=target['width'],target['height']
    sw,sh=source['canvas']['width'],source['canvas']['height']
    if min(W,H,sw,sh)<=0:return
    assets_dir=Path(assets_dir or Path(__file__).resolve().parents[1]/'brand_kit/assets')
    top=min(elements[c.backdrop]['y'] for c in cards)
    bottom=max(elements[c.backdrop]['y']+elements[c.backdrop]['height'] for c in cards)
    handled={i for c in cards for i in [c.backdrop,c.image]+c.texts}|{i for pair in actions for i in pair}
    headers=[];footers=[];backgrounds=[]
    for i,e in enumerate(elements):
        if i in handled:continue
        if e.get('rotation'):return
        if e['type']=='text':
            if e['y']+e['height']<=top+.01:headers.append(i)
            elif e['y']>=bottom-.01:footers.append(i)
            else:return
        elif (e['x']<=0 and e['y']<=0 and e['x']+e['width']>=sw and e['y']+e['height']>=sh
              and (e['type']=='shape' or e.get('fit')=='cover')):backgrounds.append(i)
        else:return
    if any(elements[a]['y']<bottom-.01 for a,b in actions):return
    if len(actions)>1:return  # A single footer action slot, not ambiguous button order.
    headers.sort(key=lambda i:(elements[i]['y'],elements[i]['x']))
    footers.sort(key=lambda i:(elements[i]['y'],elements[i]['x']))
    tall=H/W>1.3
    margin=min(W,H)*.045; gap=min(W,H)*.025; inner=W-2*margin
    scale=min(W/sw*1.2,sqrt(W*H/(sw*sh))*1.15)
    header=_fit_stack(source,headers,inner,H*.24,scale,measurer,gap*.45)
    if header is None:return
    footer_budget=min(H*.19,max(60,min(W,H)*.17)) if actions or footers else 0
    ytop=margin+header[1]+gap*1.4
    ybottom=H-margin-footer_budget-(gap if footer_budget else 0)
    available=ybottom-ytop
    if available<=0:return
    n=len(cards);cardgap=gap
    if tall:
        cw=inner;ch=(available-cardgap*(n-1))/n
    else:
        cw=(inner-cardgap*(n-1))/n;ch=available
    if min(cw,ch)<=4:return
    pad=max(2,min(cw,ch)*.075)
    if tall:
        image_width=cw*.31;text_width=cw-image_width-3*pad
        text_height=ch-2*pad
    else:
        image_height=ch*.48;text_width=cw-2*pad
        text_height=ch-image_height-3*pad
    if min(text_width,text_height)<=1:return
    # Share a common scale across all cards so longer copy cannot accidentally
    # make one product's name/price a different typographic tier.
    reference_width=sum(elements[c.texts[0]]['width'] for c in cards)/n
    card_scale=min(1.5,text_width/max(1,reference_width))
    card_plans=None
    for step in range(101):
        plans=[_text_plan(source,c.texts,text_width,card_scale,measurer,gap*.45,max(.01,1-step*.01)) for c in cards]
        if all(p is not None and p[1]<=text_height for p in plans):card_plans=plans;break
    if card_plans is None:return
    out=deepcopy(elements)
    for i in backgrounds:out[i].update(x=0.,y=0.,width=float(W),height=float(H))
    _place_stack(out,header[0],margin,margin,inner,gap*.45)
    for j,(card,plan) in enumerate(zip(cards,card_plans)):
        x=margin if tall else margin+j*(cw+cardgap)
        y=ytop+j*(ch+cardgap) if tall else ytop
        out[card.backdrop].update(x=x,y=y,width=cw,height=ch)
        if tall:
            image_slot=(x+pad,y+pad,image_width,ch-2*pad)
            tx=x+image_width+2*pad;ty=y+(ch-plan[1])/2
        else:
            image_slot=(x+pad,y+pad,cw-2*pad,image_height)
            tx=x+pad;ty=y+image_height+2*pad
        _art(out,card.image,image_slot,target,assets_dir)
        _place_stack(out,plan[0],tx,ty,text_width,gap*.45)
    fy=ybottom+gap
    if actions:
        bi,ti=actions[0];bw=min(inner, W*(.70 if tall else .36));bh=min(footer_budget*.48 if tall and footers else footer_budget*.8,min(W,H)*.09)
        pref=max(1,elements[ti]['font_size']*min(1.25,max(scale,.85)))
        padding=max(2,bh*.18)
        trial,extent=measurer.fit(elements[ti],max(1,bw-2*padding),max(1,bh-2*padding),pref)
        bx=margin if not tall else (W-bw)/2
        out[bi].update(x=bx,y=fy,width=bw,height=bh)
        out[ti].update(x=bx+padding,y=fy+(bh-extent.bottom)/2,width=bw-2*padding,
                       height=max(1,extent.bottom+1),font_size=trial['font_size'])
        fx=margin if tall else margin+bw+gap;fw=inner if tall else inner-bw-gap
        ftop=fy+bh+gap*.5 if tall else fy
        fh=H-margin-ftop
    else:fx,fw,ftop,fh=margin,inner,fy,H-margin-fy
    if footers:
        footer=_fit_stack(source,footers,fw,fh,max(.7,min(1.1,scale)),measurer,gap*.35)
        if footer is None:return
        _place_stack(out,footer[0],fx,ftop,fw,gap*.35)
    yield ('series-horizontal-cards' if tall else 'series-vertical-cards'),dict(canvas=deepcopy(target),elements=out)
