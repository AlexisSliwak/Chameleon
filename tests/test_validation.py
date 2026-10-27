import copy
import unittest
from engine.validation import validate_source, validate_target, validate_output


def source():
    return {'canvas': {'width': 100, 'height': 100}, 'elements': [
        {'id': 'heading', 'type': 'text', 'x': 10, 'y': 10, 'width': 60, 'height': 20,
         'content': 'Hello', 'font_family': 'Sans', 'font_size': 15, 'color': '#000'},
        {'id': 'photo', 'type': 'image', 'x': 10, 'y': 40, 'width': 40, 'height': 20,
         'asset_id': 'product.png'}]}


class ValidationTests(unittest.TestCase):
    def test_integral_json_numbers_are_valid_in_integer_fields(self):
        s = source()
        s['canvas'] = {'width': 100.0, 'height': 1e2}
        s['elements'][0].update(z_index=0.0, max_lines=2.0,
                                style_runs=[{'start': 0.0, 'end': 4.0}])
        self.assertEqual([], validate_source(s))
        self.assertEqual([], validate_target(s['canvas']))
        self.assertEqual([], validate_output(s, s['canvas'], copy.deepcopy(s)))

    def test_integer_fields_reject_fractional_nonfinite_and_boolean_values(self):
        for value in (1.5, True, False, '1', float('nan'), float('inf'), -float('inf')):
            with self.subTest(value=value):
                self.assertTrue(validate_target({'width': value, 'height': 100}))
                for field in ('z_index', 'max_lines'):
                    s = source()
                    s['elements'][0][field] = value
                    self.assertTrue(validate_source(s))
                for field in ('start', 'end'):
                    s = source()
                    s['elements'][0]['style_runs'] = [{'start': 0, 'end': 4, field: value}]
                    self.assertTrue(validate_source(s))

    def test_valid_and_geometry_changes(self):
        s = source()
        o = copy.deepcopy(s)
        o['elements'][0]['font_size'] = 12
        o['elements'][1].update(width=20, height=10)
        self.assertEqual([], validate_output(s, s['canvas'], o))

    def test_duplicate_ids_cannot_pass_set_comparison(self):
        s = source()
        o = copy.deepcopy(s)
        o['elements'].append(copy.deepcopy(o['elements'][0]))
        self.assertTrue(any('exactly once' in e for e in validate_output(s, s['canvas'], o)))

    def test_missing_or_invented_element(self):
        s = source()
        o = copy.deepcopy(s)
        o['elements'][1]['id'] = 'new'
        self.assertTrue(any('multiset' in e for e in validate_output(s, s['canvas'], o)))

    def test_fixed_fields_and_tied_order(self):
        for field, value in [('content', 'Changed'), ('font_family', 'Other'),
                             ('color', '#fff'), ('opacity', 0)]:
            with self.subTest(field=field):
                s = source()
                o = copy.deepcopy(s)
                o['elements'][0][field] = value
                self.assertTrue(validate_output(s, s['canvas'], o))
        s = source()
        o = copy.deepcopy(s)
        o['elements'].reverse()
        self.assertTrue(any('stacking' in e for e in validate_output(s, s['canvas'], o)))

    def test_rotated_bounds_not_unrotated_box(self):
        s = source()
        s['elements'][0].update(x=0, y=0, width=20, height=20, rotation=45)
        self.assertEqual([], validate_source(s))  # input may intentionally bleed
        self.assertTrue(any('rotation' in e for e in validate_output(s, s['canvas'], s)))

    def test_aspect_and_cover_exception(self):
        s = source()
        o = copy.deepcopy(s)
        o['elements'][1]['width'] = 20
        self.assertTrue(any('proportions' in e for e in validate_output(s, s['canvas'], o)))
        s['elements'][1]['fit'] = o['elements'][1]['fit'] = 'cover'
        self.assertEqual([], validate_output(s, s['canvas'], o))

    def test_malformed_inputs_are_actionable(self):
        for value in [None, [], {}, {'canvas': {}, 'elements': []}]:
            self.assertTrue(validate_source(value))
        for value in [0, -1, True, 1.5, float('nan')]:
            self.assertTrue(validate_target({'width': value, 'height': 100}))
        for value in [float('nan'), float('inf'), True, 'x']:
            s = source()
            s['elements'][0]['x'] = value
            self.assertTrue(validate_source(s))

    def test_target_and_extra_fields(self):
        s = source()
        self.assertTrue(validate_output(s, {'width': 101, 'height': 100}, s))
        o = copy.deepcopy(s)
        o['diagnostics'] = {}
        self.assertTrue(validate_output(s, s['canvas'], o))

    def test_style_spans_preserved_with_official_clamping(self):
        s = source()
        s['elements'][0]['style_runs'] = [{'start': 0, 'end': 8}]
        self.assertEqual([], validate_source(s))
        self.assertEqual([], validate_output(s, s['canvas'], s))
        o = copy.deepcopy(s)
        o['elements'][0]['style_runs'][0]['end'] = 5
        self.assertTrue(validate_output(s, s['canvas'], o))


if __name__ == '__main__':
    unittest.main()
