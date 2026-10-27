"""Finite measured-layout frontiers; no rendering or continuous-optimality claims.

State rectangles are OUTER footprints, including rotation/ink overhang/padding.
Placements remain element-local boxes translated with that footprint. A caller
must encode any externally visible baseline/anchor/style distinctions in
interface: dimension-only dominance is unsound across those distinctions.
Utility is additive. Capping is a deterministic approximation, not exact search.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product, groupby
import json
import math
from typing import Hashable, Mapping, Sequence


@dataclass(frozen=True)
class State:
    width: float
    height: float
    utility: float
    placements: dict[int, dict]
    interface: Hashable = "default"

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.width, self.height, self.utility)):
            raise ValueError("State dimensions and utility must be finite")
        if self.width < 0 or self.height < 0:
            raise ValueError("State footprint dimensions must be nonnegative")
        hash(self.interface)


def _placement_key(state: State):
    return json.dumps(sorted(state.placements.items()), sort_keys=True, allow_nan=False)


def _order(state: State):
    return (state.width * state.height, state.width, state.height,
            -state.utility, repr(state.interface), _placement_key(state))


def _ordered(states):
    """Preserve exact legacy ordering; serialize placements only for real ties.

    No state-lifetime cache: callers may mutate nested placement dictionaries.
    A fresh sort must observe those changes even though State itself is frozen.
    """
    def primary(s):
        return s.width*s.height,s.width,s.height,-s.utility,repr(s.interface)
    result=[]
    for _,group in groupby(sorted(states,key=primary),key=primary):
        tied=list(group)
        if len(tied)>1:tied.sort(key=_placement_key)
        result.extend(tied)
    return result


def scaled_dimensions(element, scale):
    """Keep positive image proportions even when one side is subpixel.

    Independent minimum-side clamps distort thin images. Retain the existing
    minimum for text, shapes and degenerate image boxes that have no ratio.
    """
    width, height = element['width'] * scale, element['height'] * scale
    if element['type'] == 'image' and element['width'] > 0 and element['height'] > 0:
        return width, height
    return max(.001, width), max(.001, height)


def normalize_leaf(
    placements: Mapping[int, Mapping], utility: float = 0,
    interface: Hashable = "default", rotations: Mapping[int, float] | None = None,
) -> State:
    """Enclose rotated element boxes and translate their union to the origin.

    Rotations are clockwise degrees about box centers, from rotations when
    supplied, otherwise each placement's rotation (default zero). Rotations
    affect footprints only; no new rotation override is inserted. This encloses
    boxes, not actual glyph ink; the caller must include measured ink overhang.
    Empty input yields a zero-size state. Input mappings are never modified.
    """
    copied = {index: dict(box) for index, box in placements.items()}
    bounds = []
    for index, box in copied.items():
        x, y, w, h = (float(box[key]) for key in ("x", "y", "width", "height"))
        rotation = (rotations or {}).get(index, box.get("rotation", 0))
        if not all(math.isfinite(v) for v in (x, y, w, h, rotation)) or w < 0 or h < 0:
            raise ValueError("Leaf geometry must be finite with nonnegative sizes")
        angle = math.radians(rotation)
        ex = (abs(math.cos(angle)) * w + abs(math.sin(angle)) * h) / 2
        ey = (abs(math.sin(angle)) * w + abs(math.cos(angle)) * h) / 2
        cx, cy = x + w / 2, y + h / 2
        bounds.append((cx-ex, cy-ey, cx+ex, cy+ey))
    if not bounds:
        return State(0, 0, utility, copied, interface)
    left, top = min(b[0] for b in bounds), min(b[1] for b in bounds)
    right, bottom = max(b[2] for b in bounds), max(b[3] for b in bounds)
    for box in copied.values():
        box["x"] = float(box["x"]) - left
        box["y"] = float(box["y"]) - top
    return State(right-left, bottom-top, utility, copied, interface)


def prune_states(states: Sequence[State], cap: int | None = None) -> list[State]:
    """Return a deterministic dimension/utility frontier per exact interface.

    Equal width/height/utility states with the same interface are interchangeable
    by the caller's contract; keep a deterministic reconstruction. No tolerance
    is applied to dominance. A finite cap can discard nondominated states and
    whole interface classes: it is explicitly approximate.
    """
    _validate_cap(cap)
    result = []
    for state in _ordered(states):
        if any(_dominates(kept, state) for kept in result):
            continue
        result = [kept for kept in result if not _dominates(state, kept)]
        result.append(state)
    return _cap(result, cap, presorted=True)


def _dominates(a: State, b: State):
    return (a.interface == b.interface and a.width <= b.width
            and a.height <= b.height and a.utility >= b.utility)


def _validate_cap(cap):
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1):
        raise ValueError("cap must be a positive integer or None")


def _cap(states, cap, presorted=False):
    ordered = list(states) if presorted else _ordered(states)
    if cap is not None and len(ordered) > cap:
        selected = []
        # Extremes protect both space feasibility and utility. Distinct extremes
        # all survive when cap >= 4; this remains an approximate global beam.
        extremes = [min(ordered, key=lambda s: -s.utility),
                    ordered[0],
                    min(ordered, key=lambda s: s.width),
                    min(ordered, key=lambda s: s.height)]
        for state in extremes:
            if not any(state is kept for kept in selected) and len(selected) < cap:
                selected.append(state)
        # Spread remaining choices through the deterministic dimension ordering
        # instead of filling every slot with near-identical high-utility states.
        remaining = [s for s in ordered if not any(s is kept for kept in selected)]
        count = cap - len(selected)
        if count:
            indices = [round((i + .5) * len(remaining) / count - .5) for i in range(count)]
            selected.extend(remaining[i] for i in indices)
        return _ordered(selected)
    return ordered


def combine(
    children: Sequence[Sequence[State]], direction: str = "row", gap: float = 0,
    align: str = "start", offsets: Sequence[tuple[float, float]] | None = None,
    cap: int | None = None, prune: bool = True,
    max_width: float | None = None, max_height: float | None = None,
) -> list[State]:
    """Compose finite child alternatives, adding their utilities.

    Row/column alignment applies to outer footprints, not text baselines.
    Baseline or arbitrary anchor alignment must be computed by the caller and
    passed as overlay offsets. Overlay normalizes the union of translated child
    footprints. It does not resize child boxes. Row/column offsets are rejected
    rather than silently ignored. Repeated element indices are invalid.

    With prune=False and cap=None every finite combination is returned. Default
    pruning is valid only for context-compatible interfaces and additive utility.
    A cap triggers binary incremental merging and pruning/capping after each
    child. At most cap * len(next_child) combinations are materialized per
    merge; input alternatives and placement sizes still affect memory. This
    beam can discard states needed by a later child and is approximate.
    Optional positive finite bounds filter every prefix before capping. This
    rejection is sound because these operators never shrink an outer union;
    it does not guarantee the remaining beam contains a feasible final state.
    """
    for name, bound in (("max_width", max_width), ("max_height", max_height)):
        if bound is not None and (isinstance(bound, bool) or not isinstance(bound, (int, float))
                                  or not math.isfinite(bound) or bound <= 0):
            raise ValueError(name + " must be finite and positive or None")
    if direction not in ("row", "column", "overlay"):
        raise ValueError("direction must be row, column or overlay")
    if align not in ("start", "center", "end"):
        raise ValueError("align must be start, center or end")
    if not math.isfinite(gap) or gap < 0:
        raise ValueError("gap must be finite and nonnegative")
    _validate_cap(cap)
    if direction != "overlay" and offsets is not None:
        raise ValueError("Explicit offsets are supported only for overlay")
    if direction == "overlay" and (gap != 0 or align != "start"):
        raise ValueError("Overlay uses offsets; gap/alignment must remain default")
    if offsets is not None:
        if len(offsets) != len(children) or any(
            len(pair) != 2 or not all(math.isfinite(v) for v in pair) for pair in offsets
        ):
            raise ValueError("One finite (dx, dy) offset is required per child")
    if cap is not None and children:
        # Preserve canonical interfaces while bounding each prefix. A normalized
        # overlay prefix is placed back at its common-coordinate origin before
        # adding the next child, so negative offsets remain correct.
        initial_offsets = offsets[:1] if offsets is not None else None
        partial = combine(children[:1], direction, gap, align, initial_offsets, prune=prune,
                          max_width=max_width, max_height=max_height)
        partial = prune_states(partial, cap) if prune else _cap(partial, cap)
        for index, alternatives in enumerate(children[1:], 1):
            merged = []
            for prefix in partial:
                for child in alternatives:
                    pair_offsets = None
                    if direction == "overlay" and offsets is not None:
                        origin = (min(p[0] for p in offsets[:index]),
                                  min(p[1] for p in offsets[:index]))
                        pair_offsets = [origin, offsets[index]]
                    pair_options = combine([[prefix], [child]], direction, gap, align,
                                           pair_offsets, prune=False,
                                           max_width=max_width, max_height=max_height)
                    if not pair_options:
                        continue
                    pair = pair_options[0]
                    signature = (direction, align, gap,
                                 tuple(tuple(p) for p in offsets[:index+1]) if offsets is not None else None,
                                 prefix.interface[-1] + (child.interface,))
                    merged.append(State(pair.width, pair.height, pair.utility,
                                        pair.placements, signature))
            partial = prune_states(merged, cap) if prune else _cap(merged, cap)
        return partial
    states = []
    for choice in product(*children):
        if not choice:
            states.append(State(0, 0, 0, {}, (direction, align, ())))
            continue
        if direction == "overlay":
            positions = list(offsets) if offsets is not None else [(0, 0)] * len(choice)
        else:
            cross = max(s.height if direction == "row" else s.width for s in choice)
            positions, cursor = [], 0
            factor = {"start": 0, "center": .5, "end": 1}[align]
            for state in choice:
                shift = factor * (cross - (state.height if direction == "row" else state.width))
                positions.append((cursor, shift) if direction == "row" else (shift, cursor))
                cursor += (state.width if direction == "row" else state.height) + gap
        left = min(p[0] for p in positions)
        top = min(p[1] for p in positions)
        right = max(p[0] + s.width for p, s in zip(positions, choice))
        bottom = max(p[1] + s.height for p, s in zip(positions, choice))
        placements = {}
        for state, (dx, dy) in zip(choice, positions):
            if placements.keys() & state.placements.keys():
                raise ValueError("A composition cannot repeat an element index")
            for index, original in state.placements.items():
                box = dict(original)
                box["x"] = box["x"] + dx - left
                box["y"] = box["y"] + dy - top
                placements[index] = box
        signature = (direction, align, gap, tuple(tuple(pair) for pair in offsets) if offsets is not None else None,
                     tuple(s.interface for s in choice))
        states.append(State(right-left, bottom-top, sum(s.utility for s in choice), placements, signature))
    states = [state for state in states
              if (max_width is None or state.width <= max_width)
              and (max_height is None or state.height <= max_height)]
    return prune_states(states, cap) if prune else _cap(states, cap)
