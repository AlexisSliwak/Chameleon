"""Source-relative composition checks, not an aesthetic or subject-recognition model.

No element names or copy strings determine roles. Visible image support is
sampled through the official fit adapter; it accounts for alpha padding, not
occlusion by later layers. Numeric thresholds are engineering preferences.
"""
from functools import lru_cache
from collections import Counter, defaultdict
import math
from pathlib import Path
from statistics import median
from stat import S_ISREG

from renderer.converter.assets import load_asset_image

DEFAULT_ASSETS = Path(__file__).resolve().parents[1] / 'brand_kit/assets'


def _area(box):
    return max(0., box[2] - box[0]) * max(0., box[3] - box[1])


def _rotate_box(element, box):
    angle = math.radians(element.get('rotation', 0))
    c, s = math.cos(angle), math.sin(angle)
    cx, cy = element['width'] / 2, element['height'] / 2
    points = [(element['x'] + cx + (x-cx)*c - (y-cy)*s,
               element['y'] + cy + (x-cx)*s + (y-cy)*c)
              for x in (box[0], box[2]) for y in (box[1], box[3])]
    return min(x for x, y in points), min(y for x, y in points), max(x for x, y in points), max(y for x, y in points)


@lru_cache(maxsize=512)
def _alpha_support(asset, mtime, size, sample_width, sample_height, fit):
    # Cache on the actual raster dimensions, not unbounded floating box sizes.
    # Uniformly scaled large images with the same aspect reuse one fitted mask.
    image = load_asset_image(str(Path(asset).parent), Path(asset).name,
                             sample_width, sample_height, fit)
    alpha = image.getchannel('A')
    bounds = alpha.point(lambda value: 255 if value >= 16 else 0).getbbox()
    if bounds is None:
        return (0., 0., 0., 0.), 0.
    box = (bounds[0]/image.width, bounds[1]/image.height,
           bounds[2]/image.width, bounds[3]/image.height)
    support = sum(index * count for index, count in enumerate(alpha.histogram())) / (255 * image.width * image.height)
    return box, support


def visible_image(element, assets_dir):
    """Return world-space alpha bounds and approximate alpha-weighted area.

    Missing assets contribute no hero evidence, rather than treating a rendered
    error placeholder as a major brand subject. Their preservation is checked
    by the independent validator, not excused by this quality metric.
    """
    w, h = element['width'], element['height']
    path = (Path(assets_dir) / element['asset_id']).absolute()
    try:
        stat = path.stat()
    except OSError:
        stat = None
    if w <= 0 or h <= 0 or stat is None or not S_ISREG(stat.st_mode):
        return (element['x'], element['y'], element['x'], element['y']), 0.
    scale = min(1., 192 / max(w, h, 1))
    sample_width, sample_height = max(1, round(w*scale)), max(1, round(h*scale))
    box, support = _alpha_support(str(path), stat.st_mtime_ns, stat.st_size,
                                  sample_width, sample_height, element.get('fit', 'contain'))
    local = (box[0]*w, box[1]*h, box[2]*w, box[3]*h)
    return _rotate_box(element, local), support*w*h*element.get('opacity', 1)


def optical_bounds(element, assets_dir=None):
    """Alpha-support bounds after official contain/cover fit and rotation.

    This is a sampled foreground footprint, not final composited visibility.
    Missing assets have an opaque official placeholder, hence their full box.
    Non-image elements use their full rotated box; text needs measured ink.
    """
    assets = Path(assets_dir) if assets_dir is not None else DEFAULT_ASSETS
    if element['type'] != 'image' or not (assets / element['asset_id']).is_file():
        return _rotate_box(element, (0, 0, element['width'], element['height']))
    return visible_image(element, assets)[0]


def _text_info(element, measurer):
    extent = measurer.measure(element)
    box = _rotate_box(element, (extent.left, extent.top, extent.right, extent.bottom))
    effective = min(element['font_size'], max(0., extent.bottom-extent.top) / max(1, extent.lines))
    return box, effective


def _shortfall(actual, desired):
    return min(5., max(0., math.log(max(desired, 1e-6) / max(actual, 1e-6))))


def _distance(a, b, width, height):
    return math.hypot(((a[0]+a[2])-(b[0]+b[2]))/(2*width),
                      ((a[1]+a[3])-(b[1]+b[3]))/(2*height))


def _union(boxes):
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


def repeated_group_flow(source, design):
    """Soft flow checks only for explicit, structurally repeated source rows.

    Mixed source layouts are deliberately unclassified. A clear source row can
    reflow to ordered columns or row-major grids. Group names and literal text
    are identifiers only, never role labels. All penalties are bounded averages.
    """
    original = {e['id']: e for e in source['elements']}
    output = {e['id']: e for e in design['elements']}
    groups = defaultdict(list)
    for e in source['elements']:
        if e.get('group_id') is not None:
            groups[e['group_id']].append(e)
    series = defaultdict(list)
    def box(elements):
        return _union([_rotate_box(e, (0, 0, e['width'], e['height'])) for e in elements])
    for gid, elements in groups.items():
        counts = Counter(e['type'] for e in elements)
        if len(elements) >= 2 and counts['text']:
            signature = tuple(sorted(counts.items()))
            series[signature].append((gid, elements, box(elements)))
    order_losses, scale_losses, intrusions = [], [], []
    for peers in series.values():
        if len(peers) < 2:
            continue
        peers.sort(key=lambda item: (item[2][0], item[2][1]))
        heights = [max(1e-6, p[2][3]-p[2][1]) for p in peers]
        centers = [(p[2][1]+p[2][3])/2 for p in peers]
        if max(centers)-min(centers) > .3*median(heights):
            continue
        if any(a[2][2] > b[2][0] + .05*min(a[2][2]-a[2][0], b[2][2]-b[2][0]) for a, b in zip(peers, peers[1:])):
            continue
        dst = [(gid, box([output[e['id']] for e in elements])) for gid, elements, src in peers]
        source_order = {gid: i for i, (gid, elements, src) in enumerate(peers)}
        # Tolerant row-major reading order; reflow to a column remains ordered.
        tolerance = .25*median(max(1e-6, b[3]-b[1]) for gid, b in dst)
        pending = sorted(dst, key=lambda item: (item[1][1], item[1][0]))
        reading = []
        while pending:
            top = pending[0][1][1]
            row = [item for item in pending if item[1][1] <= top+tolerance]
            pending = [item for item in pending if item[1][1] > top+tolerance]
            reading.extend(sorted(row, key=lambda item: item[1][0]))
        indices = [source_order[gid] for gid, bounds in reading]
        inversions = sum(a>b for i, a in enumerate(indices) for b in indices[i+1:])
        order_losses.append(inversions/max(1, len(peers)*(len(peers)-1)/2))
        scales = [math.sqrt(max(1e-6, _area(dest))/max(1e-6, _area(src)))
                  for (gid, elements, src), (_, dest) in zip(peers, dst)]
        scale_losses.append(min(2., max(0., math.log(max(scales)/max(min(scales), 1e-6))-math.log(1.35))))
        src_union = _union([p[2] for p in peers])
        dst_union = _union([b for gid, b in dst])
        members = {e['id'] for gid, elements, src in peers for e in elements}
        # Evaluate other text-bearing units once; do not count every CTA span.
        outsiders = defaultdict(list)
        for e in source['elements']:
            if e['id'] not in members:
                key = ('g', e['group_id']) if e.get('group_id') is not None else ('e', e['id'])
                outsiders[key].append(e)
        intrusion_count = 0
        def inside_center(bounds, container):
            x, y = (bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2
            return container[0] < x < container[2] and container[1] < y < container[3]
        for elements in outsiders.values():
            if not any(e['type']=='text' and e.get('content','').strip() for e in elements):
                continue
            src_box = box(elements)
            dst_box = box([output[e['id']] for e in elements])
            if (not inside_center(src_box, src_union) and inside_center(dst_box, dst_union)
                    and not any(inside_center(dst_box, peer_box) for gid, peer_box in dst)):
                intrusion_count += 1
        intrusions.append(min(1., intrusion_count/max(1, len(peers)-1)))
    return {'repeated_series_count': len(order_losses),
            'peer_order_loss': sum(order_losses)/max(1, len(order_losses)),
            'peer_scale_loss': sum(scale_losses)/max(1, len(scale_losses)),
            'series_intrusion_loss': sum(intrusions)/max(1, len(intrusions))}


def composition_metrics(source, design, measurer, assets_dir=None):
    """Return finite diagnostic terms and a score (larger is preferred).

    The score rewards meeting readable copy/headline floors, not making every
    font arbitrarily large. It penalizes shrinking source-prominent imagery,
    source text-hierarchy reversal, and dissociating previously close content.
    Validation and actual rendered inspection remain separate prerequisites.
    """
    assets = Path(assets_dir) if assets_dir is not None else DEFAULT_ASSETS
    sw, sh = source['canvas']['width'], source['canvas']['height']
    tw, th = design['canvas']['width'], design['canvas']['height']
    area_scale = math.sqrt(tw*th/(sw*sh))
    original = {e['id']: e for e in source['elements']}
    output = {e['id']: e for e in design['elements']}
    if original.keys() != output.keys():
        raise ValueError('composition requires the same element IDs; validate first')
    text, images, source_boxes, target_boxes = [], [], {}, {}
    for eid, old in original.items():
        current = output[eid]
        if old['type'] == 'text' and old['content'].strip():
            src_box, src_effective = _text_info(old, measurer)
            dst_box, dst_effective = _text_info(current, measurer)
            text.append((eid, src_effective, dst_effective))
            source_boxes[eid], target_boxes[eid] = src_box, dst_box
        elif old['type'] == 'image':
            # Full-canvas imagery is a backdrop, not a foreground hero.
            covers = old['x'] <= 0 and old['y'] <= 0 and old['x']+old['width'] >= sw and old['y']+old['height'] >= sh
            if covers and old.get('fit') == 'cover' and old.get('group_id') is None:
                continue
            src_box, src_area = visible_image(old, assets)
            dst_box, dst_area = visible_image(current, assets)
            if src_area > 0:
                images.append((eid, src_box, src_area, dst_area))
                source_boxes[eid], target_boxes[eid] = src_box, dst_box
        elif old['type'] == 'shape' and old.get('group_id') is not None:
            source_boxes[eid] = _rotate_box(old, (0, 0, old['width'], old['height']))
            target_boxes[eid] = _rotate_box(current, (0, 0, current['width'], current['height']))
    # Large source-visible subjects carry more weight than tiny decorations.
    image_total = sum(value[2] for value in images)
    hero_loss = balance_loss = 0.
    headline = max(text, key=lambda value: original[value[0]]['font_size'], default=None)
    for eid, box, src_area, dst_area in images:
        weight = src_area / image_total
        element = original[eid]
        full_box = _rotate_box(element, (0, 0, element['width'], element['height']))
        max_fit = min(tw/max(full_box[2]-full_box[0], 1e-6), th/max(full_box[3]-full_box[1], 1e-6))
        expected_scale = min(area_scale, max_fit)
        hero_loss += weight * .5 * _shortfall(dst_area, src_area*expected_scale**2)
        if headline:
            text_scale = output[headline[0]]['font_size'] / original[headline[0]]['font_size']
            image_scale = math.sqrt(max(dst_area, 1e-6)/src_area)
            balance_loss += weight * _shortfall(image_scale*1.6, text_scale)
    # Every copy span matters, including the smallest; no average-font reward.
    desired_floor = min(12., max(8., th*.1))
    copy_losses = [_shortfall(dst, min(src, desired_floor)) for eid, src, dst in text if src > 0]
    copy_loss = .5*(sum(copy_losses)/max(1, len(copy_losses)) + max(copy_losses, default=0))
    heading_loss = 0.
    if headline:
        eid, src_eff, dst_eff = headline
        desired = min(src_eff, max(desired_floor*1.8, src_eff*min(1., area_scale)))
        heading_loss = _shortfall(dst_eff, desired)
    hierarchy_terms = []
    for i, (aid, a_src, a_dst) in enumerate(text):
        for bid, b_src, b_dst in text[i+1:]:
            a, b = original[aid]['font_size'], original[bid]['font_size']
            if max(a, b) < min(a, b)*1.15:
                continue
            big, small = (aid, bid) if a > b else (bid, aid)
            ratio = original[big]['font_size']/original[small]['font_size']
            new_ratio = output[big]['font_size']/output[small]['font_size']
            # Preserve most of the distinction, not every original point size.
            hierarchy_terms.append(_shortfall(new_ratio, ratio**.65))
    hierarchy_loss = sum(hierarchy_terms)/max(1, len(hierarchy_terms))
    # Existing group members should not become disconnected. Compare normalized
    # center distances, allowing reflow and substantial aspect changes.
    cohesion_terms, alignment_terms = [], []
    ids = list(source_boxes)
    for i, aid in enumerate(ids):
        a, ao = source_boxes[aid], target_boxes[aid]
        others = [bid for bid in ids if bid != aid]
        if others:
            bid = min(others, key=lambda key: _distance(a, source_boxes[key], sw, sh))
            distance = _distance(a, source_boxes[bid], sw, sh)
            cohesion_terms.append(max(0., _distance(ao, target_boxes[bid], tw, th)-distance*1.8-.08))
        for bid in ids[i+1:]:
            b, bo = source_boxes[bid], target_boxes[bid]
            if original[aid].get('group_id') is not None and original[aid].get('group_id') == original[bid].get('group_id'):
                distance = _distance(a, b, sw, sh)
                cohesion_terms.append(2*max(0., _distance(ao, bo, tw, th)-distance*1.5-.04))
            for pos in (0, 2):
                if abs(a[pos]-b[pos])/sw <= .008:
                    alignment_terms.append(min(.3, abs(ao[pos]-bo[pos])/tw))
    cohesion = sum(cohesion_terms)/max(1, len(cohesion_terms))
    alignment = sum(alignment_terms)/max(1, len(alignment_terms))
    # Saturated readability scores alone can turn a sparse vertical source
    # into a disconnected horizontal strip. Preserve its established anchors
    # most strongly near the source aspect; allow larger moves for real reflow.
    # Dense compositions have more relationships than absolute anchors can
    # express: their cohesion/flow terms govern instead. Broad anchor weighting
    # fragmented a multi-block portrait in development evaluation.
    aspect_agreement = min((tw/th)/(sw/sh),(sw/sh)/(tw/th))
    anchor = sum(abs((target_boxes[eid][0]+target_boxes[eid][2])/(2*tw)
                     -(source_boxes[eid][0]+source_boxes[eid][2])/(2*sw))
                 +abs((target_boxes[eid][1]+target_boxes[eid][3])/(2*th)
                      -(source_boxes[eid][1]+source_boxes[eid][3])/(2*sh))
                 for eid in source_boxes)/max(1,len(source_boxes))
    anchor = anchor if len(source_boxes)<=3 else 0.
    flow = repeated_group_flow(source, design)
    score = (-3*hero_loss -1.5*balance_loss -2*hierarchy_loss -2*copy_loss -heading_loss
             -.5*cohesion -.25*alignment -2*flow['peer_order_loss']
             -flow['peer_scale_loss'] -1.5*flow['series_intrusion_loss'] -1.5*aspect_agreement*anchor)
    return {'score': score, 'hero_retention': math.exp(-hero_loss),
            'hero_text_balance_loss': balance_loss, 'headline_retention': math.exp(-heading_loss),
            'copy_floor_loss': copy_loss, 'minimum_effective_copy_px': min((x[2] for x in text), default=0.),
            'hierarchy_loss': hierarchy_loss, 'cohesion_loss': cohesion, 'alignment_loss': alignment,
            'source_anchor_loss': anchor*aspect_agreement,
            'foreground_image_count': len(images), 'text_count': len(text), **flow}
