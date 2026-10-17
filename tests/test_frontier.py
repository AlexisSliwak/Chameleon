"""Independent finite-oracle and reconstructed-geometry checks; stdlib only."""
import copy
import itertools
import math
import unittest

from engine.frontier import State, combine, normalize_leaf, prune_states


def leaf(index, w, h, utility=0, interface="default"):
    return State(w, h, utility, {index: dict(x=0, y=0, width=w, height=h, font_size=12)}, interface)


class FrontierTests(unittest.TestCase):
    def test_fixed_tree_matches_independent_finite_oracle(self):
        alternatives = [[leaf(0, 2, 6, 1), leaf(0, 5, 2, 3)],
                        [leaf(1, 3, 4, 2), leaf(1, 6, 1, 4)],
                        [leaf(2, 4, 2, 2), leaf(2, 2, 5, 3)]]
        # Tree: column(row(A,B,gap=1),C,gap=2). Independent arithmetic
        # enumerates the full domain; it does not use production merge/prune.
        raw = []
        for a, b, c in itertools.product(*alternatives):
            raw.append((max(a.width+b.width+1, c.width),
                        max(a.height, b.height)+c.height+2,
                        a.utility+b.utility+c.utility))
        expected = {s for s in raw if not any(
            t != s and t[0] <= s[0] and t[1] <= s[1] and t[2] >= s[2]
            for t in raw)}
        row = combine(alternatives[:2], gap=1)
        actual = combine([row, alternatives[2]], direction="column", gap=2)
        self.assertEqual(expected, {(s.width, s.height, s.utility) for s in actual})
        for state in actual:
            self.assertEqual({0, 1, 2}, set(state.placements))
            for box in state.placements.values():
                self.assertGreaterEqual(box['x'], 0)
                self.assertGreaterEqual(box['y'], 0)
                self.assertLessEqual(box['x']+box['width'], state.width)
                self.assertLessEqual(box['y']+box['height'], state.height)
                self.assertEqual(12, box['font_size'])

    def test_exhaustive_mode_and_cap(self):
        children = [[leaf(0, 2, 6), leaf(0, 6, 2)], [leaf(1, 1, 1), leaf(1, 2, 2)]]
        self.assertEqual(4, len(combine(children, prune=False)))
        full = combine(children)
        capped = combine(children, cap=1)
        self.assertEqual(1, len(capped))
        self.assertIn(capped[0], full)
        self.assertEqual(capped, combine([list(reversed(c)) for c in children], cap=1))

    def test_interfaces_prevent_unsound_pruning(self):
        a = leaf(0, 2, 2, 4, ('baseline', 1))
        b = leaf(0, 3, 3, 1, ('baseline', 2))
        c = leaf(0, 3, 3, 1, ('baseline', 1))
        self.assertEqual([a, b], prune_states([c, b, a]))

    def test_overlay_offsets_and_baseline_union(self):
        # Baselines at 8 and 2: shift second by 6; required height 12, not max(10,6).
        a, b = leaf(0, 4, 10), leaf(1, 3, 6)
        state = combine([[a], [b]], direction='overlay', offsets=[(-5, 0), (2, 6)])[0]
        self.assertEqual((10, 12), (state.width, state.height))
        self.assertEqual((0, 0), (state.placements[0]['x'], state.placements[0]['y']))
        self.assertEqual((7, 6), (state.placements[1]['x'], state.placements[1]['y']))

    def test_rotated_leaf_and_nested_reconstruction(self):
        original = {0: dict(x=-4, y=7, width=2, height=6, font_size=17)}
        before = copy.deepcopy(original)
        rotated = normalize_leaf(original, rotations={0: 90})
        self.assertAlmostEqual(6, rotated.width)
        self.assertAlmostEqual(2, rotated.height)
        nested = combine([[rotated], [leaf(1, 3, 4)]], gap=2, align='end')[0]
        self.assertAlmostEqual(11, nested.width)
        self.assertAlmostEqual(4, nested.height)
        self.assertEqual(before, original)
        self.assertEqual(17, nested.placements[0]['font_size'])
        # Independent rotated corners lie inside the declared outer footprint.
        box = nested.placements[0]
        cx, cy = box['x']+1, box['y']+3
        for dx, dy in itertools.product((-1, 1), (-3, 3)):
            x, y = cx-dy, cy+dx
            self.assertGreaterEqual(x, -1e-12)
            self.assertLessEqual(x, nested.width+1e-12)
            self.assertGreaterEqual(y, -1e-12)
            self.assertLessEqual(y, nested.height+1e-12)

    def test_center_column_and_footprint_padding(self):
        a = State(10, 4, 0, {0: dict(x=2, y=1, width=6, height=2)})
        b = leaf(1, 4, 2)
        result = combine([[a], [b]], direction='column', gap=3, align='center')[0]
        self.assertEqual((10, 9), (result.width, result.height))
        self.assertEqual((3, 7), (result.placements[1]['x'], result.placements[1]['y']))
        self.assertEqual((2, 1), (result.placements[0]['x'], result.placements[0]['y']))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            combine([[leaf(0, 1, 1)], [leaf(0, 1, 1)]])
        for cap in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                prune_states([], cap)
        with self.assertRaises(ValueError):
            State(math.inf, 1, 0, {})
        with self.assertRaises(ValueError):
            combine([[leaf(0, 1, 1)]], offsets=[(1, 2)])
        self.assertEqual([], combine([[]]))
        self.assertEqual(0, combine([])[0].width)


class IncrementalFrontierTests(unittest.TestCase):
    def test_uncapped_and_large_cap_agree_on_centered_and_offset_geometry(self):
        children = [[leaf(0, 2, 4), leaf(0, 4, 2)],
                    [leaf(1, 3, 1), leaf(1, 1, 3)], [leaf(2, 2, 2)]]
        for direction, kwargs in [('row', {'align':'center', 'gap':2}),
                                  ('column', {'align':'end', 'gap':1}),
                                  ('overlay', {'offsets':[(-4, 3), (2, -6), (7, 1)]})]:
            with self.subTest(direction=direction):
                expected = combine(children, direction=direction, prune=False, **kwargs)
                actual = combine(children, direction=direction, cap=100, prune=False, **kwargs)
                self.assertEqual(expected, actual)

    def test_cap_handles_large_cartesian_input(self):
        # 8**12 complete combinations cannot reasonably be enumerated. The
        # result checks observable reconstruction, not internal call counts.
        children = [[leaf(i, k+1, 9-k, k) for k in range(8)] for i in range(12)]
        states = combine(children, cap=6)
        self.assertLessEqual(len(states), 6)
        for state in states:
            self.assertEqual(set(range(12)), set(state.placements))


class DiverseCapTests(unittest.TestCase):
    def test_extreme_states_survive_cap_four(self):
        options = [leaf(0,1,15,2), leaf(0,15,1,2), leaf(0,3,3,1),
                   leaf(0,20,20,50), leaf(0,5,7,10), leaf(0,7,5,10)]
        chosen = prune_states(options, cap=4)
        self.assertEqual({(1,15),(15,1),(3,3),(20,20)},
                         {(s.width,s.height) for s in chosen})

    def test_tiny_feasible_prefix_survives_bigger_high_utility_options(self):
        options = [leaf(0,1,1,1)] + [leaf(0,k,k,10*k) for k in range(2,25)]
        states = combine([options, [leaf(1,1,1)]], cap=4)
        self.assertTrue(any(s.width <= 3 and s.height <= 1 for s in states))


class TargetBoundTests(unittest.TestCase):
    def test_bounds_filter_before_cap_saves_feasible_prefix(self):
        options = [leaf(0, 2, 2, 1), leaf(0, 100, 100, 100)]
        children = [options, [leaf(1, 2, 2)]]
        unbounded = combine(children, cap=1)
        self.assertFalse(any(s.width <= 5 and s.height <= 3 for s in unbounded))
        bounded = combine(children, cap=1, max_width=5, max_height=3)
        self.assertEqual(1, len(bounded))
        self.assertEqual((4, 2), (bounded[0].width, bounded[0].height))
        self.assertEqual({0, 1}, set(bounded[0].placements))

    def test_bounded_exhaustive_matches_independent_dimension_filter(self):
        children = [[leaf(0, 2, 5), leaf(0, 5, 2)],
                    [leaf(1, 3, 1), leaf(1, 1, 3)], [leaf(2, 2, 2)]]
        for direction, extra in [('row', {'gap':1, 'align':'center'}),
                                 ('column', {'gap':2, 'align':'end'}),
                                 ('overlay', {'offsets':[(-4, 3), (2, -2), (0, 1)]})]:
            with self.subTest(direction=direction):
                # Full unbounded geometry is covered by independent oracle and
                # corner tests above; filtering here tests that prefix rejection
                # never loses a fitting full composition.
                full = combine(children, direction=direction, prune=False, **extra)
                expected = [s for s in full if s.width <= 9 and s.height <= 9]
                for cap in (None, 100):
                    result = combine(children, direction=direction, prune=False, cap=cap,
                                     max_width=9, max_height=9, **extra)
                    self.assertEqual(expected, result)

    def test_invalid_target_bounds_rejected(self):
        for name in ('max_width', 'max_height'):
            for bound in (0, -1, math.inf, math.nan, True, '5'):
                with self.subTest(name=name, bound=bound):
                    with self.assertRaises(ValueError):
                        combine([[leaf(0, 1, 1)]], **{name:bound})
        self.assertEqual([], combine([[leaf(0, 3, 4)]], max_width=2))


if __name__ == '__main__':
    unittest.main()
