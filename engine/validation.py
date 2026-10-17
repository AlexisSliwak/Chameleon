"""Independent contract checks; strict bounds/style checks are engine policy.

This checks the archived schema's structure and our declared preservation profile,
not visual readability or Adobe's undisclosed scoring rubric.
"""
import json
import math
from collections import Counter
from pathlib import Path

_SCHEMA = json.loads((Path(__file__).resolve().parents[1] / 'chameleon_design_schema_v0.9.json').read_text())
_EDITABLE = {'x', 'y', 'width', 'height', 'font_size'}


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_type(value, name):
    return {'object': lambda: isinstance(value, dict),
            'array': lambda: isinstance(value, list),
            'string': lambda: isinstance(value, str),
            'number': lambda: _finite_number(value),
            'integer': lambda: type(value) is int and _finite_number(value),
            'null': lambda: value is None}[name]()


def _check(value, schema, path, errors):
    if '$ref' in schema:
        schema = _SCHEMA['$defs'][schema['$ref'].split('/')[-1]]
    types = schema.get('type')
    if types and not any(_is_type(value, t) for t in ([types] if isinstance(types, str) else types)):
        errors.append(f'{path}: expected {types} (finite numeric values required)')
        return
    if 'enum' in schema and value not in schema['enum']:
        errors.append(f'{path}: unsupported value {value!r}')
    if type(value) in (int, float):
        for bound, op in [('minimum', lambda a, b: a < b), ('maximum', lambda a, b: a > b)]:
            if bound in schema and op(value, schema[bound]):
                errors.append(f'{path}: violates {bound} {schema[bound]}')
    if isinstance(value, dict):
        for field in schema.get('required', []):
            if field not in value:
                errors.append(f'{path}.{field}: required field missing')
        props = schema.get('properties', {})
        if schema.get('additionalProperties') is False:
            for field in value.keys() - props.keys():
                errors.append(f'{path}.{field}: unexpected field')
        for field, spec in props.items():
            if field in value:
                _check(value[field], spec, f'{path}.{field}', errors)
        for clause in schema.get('allOf', []):
            condition = clause['if']['properties']['type']['const']
            if value.get('type') == condition:
                _check(value, clause['then'], path, errors)
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            errors.append(f'{path}: requires at least {schema["minItems"]} item(s)')
        for i, item in enumerate(value):
            if 'items' in schema:
                _check(item, schema['items'], f'{path}[{i}]', errors)


def validate_target(target):
    errors = []
    _check(target, _SCHEMA['$defs']['canvas'], 'target_canvas', errors)
    return errors


def validate_source(source):
    """Validate input shape; original decorative bleed is allowed as input."""
    errors = []
    _check(source, _SCHEMA, 'design', errors)
    if errors:
        return errors
    ids = Counter(e['id'] for e in source['elements'])
    for eid, count in ids.items():
        if count != 1:
            errors.append(f'element {eid!r}: ID occurs {count} times; expected exactly once')
    # The official core fixture has an overlong style span. The converter clamps
    # it, and the provisional schema requires only nonnegative integer indices.
    # Preserve spans exactly rather than reject supported organizer input.
    return errors


def rotated_bounds(element):
    """Axis-aligned bounds of the rotated rectangle, in canvas pixels."""
    angle = math.radians(element.get('rotation', 0))
    w, h = element['width'], element['height']
    ex = (abs(math.cos(angle)) * w + abs(math.sin(angle)) * h) / 2
    ey = (abs(math.sin(angle)) * w + abs(math.cos(angle)) * h) / 2
    cx, cy = element['x'] + w / 2, element['y'] + h / 2
    return cx - ex, cy - ey, cx + ex, cy + ey


def validate_output(source, target, output):
    """Return actionable errors, including explicitly labeled policy failures.

    Aspect tolerance is numerical noise only, not an asserted organizer threshold.
    Existing cover images are exempt from box-aspect preservation, not asset identity.
    """
    errors = validate_source(source) + validate_target(target)
    if errors:
        return errors
    errors = validate_source(output)
    if errors:
        return errors
    if output['canvas'] != target:
        errors.append('canvas: output must equal requested target_canvas')
    original = {e['id']: e for e in source['elements']}
    if Counter(original.keys()) != Counter(e['id'] for e in output['elements']):
        errors.append('elements: source/output ID multiset mismatch')
        return errors
    # List order breaks tied z-index ties in the official renderer.
    before_order = [e['id'] for e in sorted(source['elements'], key=lambda e: e.get('z_index', 0))]
    after_order = [e['id'] for e in sorted(output['elements'], key=lambda e: e.get('z_index', 0))]
    if before_order != after_order:
        errors.append('policy: effective stacking order changed')
    for e in output['elements']:
        old = original[e['id']]
        editable = _EDITABLE if old['type'] == 'text' else _EDITABLE - {'font_size'}
        fixed_old = {k: v for k, v in old.items() if k not in editable}
        fixed_new = {k: v for k, v in e.items() if k not in editable}
        if fixed_old != fixed_new:
            changed = sorted(k for k in fixed_old.keys() | fixed_new.keys()
                             if k not in fixed_old or k not in fixed_new or fixed_old[k] != fixed_new[k])
            errors.append(f'element {e["id"]!r}: fixed content/style policy changed: {changed}')
        left, top, right, bottom = rotated_bounds(e)
        if not all(math.isfinite(v) for v in (left, top, right, bottom)) or left < -1e-6 or top < -1e-6 or right > target['width'] + 1e-6 or bottom > target['height'] + 1e-6:
            errors.append(f'element {e["id"]!r}: strict bounds policy violated after rotation')
        if old['type'] == 'image' and old.get('fit', 'contain') != 'cover':
            if old['width'] > 0 and old['height'] > 0:
                if e['width'] <= 0 or e['height'] <= 0 or not math.isclose(
                        e['width'] * old['height'], e['height'] * old['width'], rel_tol=1e-6, abs_tol=1e-8):
                    errors.append(f'element {e["id"]!r}: ordinary image proportions changed')
    return errors
