import csv
import json
from pathlib import Path
import tempfile
import unittest
from scripts.blind_review import create,summarize,FIELDS


class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.before=self.root/'old';self.after=self.root/'new'
        for folder,value in ((self.before,b'old'),(self.after,b'new')):
            folder.mkdir();(folder/'output.png').write_bytes(value)
            (folder/'source.png').write_bytes(b'same source')
            (folder/'output.json').write_text('{}')
            (folder/'results.json').write_text(json.dumps(dict(cases=[dict(id='family--target',fixture='family.json',target=dict(width=100,height=100),status='checks-passed',png='output.png',json='output.json',source_png='source.png')])))
        self.output=self.root/'pack'

    def test_anonymous_pairs_keep_source_and_separate_answer_key(self):
        key=create(self.before,self.after,self.output,17)
        directory=self.output/'reviewer'
        page=(directory/'index.html').read_text()
        self.assertNotIn('family--target',page)
        self.assertNotIn('answer-key',page)
        self.assertEqual((directory/'case-001-source.png').read_bytes(),b'same source')
        for label,mapping in key[0]['labels'].items():
            expected=b'old' if mapping['method']=='before' else b'new'
            self.assertEqual((directory/f'case-001-{label}.png').read_bytes(),expected)
        result=summarize(self.output/'answer-key.json',directory/'ratings.csv')
        self.assertEqual(result['counts']['unrated'],1)
        self.assertEqual(result['counts']['after'],0)

    def test_ratings_decode_and_retain_severe_failures(self):
        key=create(self.before,self.after,self.output,3)
        winner=next(label for label,item in key[0]['labels'].items() if item['method']=='after')
        path=self.output/'reviewer/ratings.csv'
        with path.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
            w.writerow(dict(case='case-001',preference=winner,severe_failure='both',notes='Tiny text in both'))
        result=summarize(self.output/'answer-key.json',path)
        self.assertEqual(result['counts']['after'],1)
        self.assertEqual(len(result['severe_failures']),1)
        self.assertEqual(result['families']['family.json']['after'],1)

    def test_missing_output_or_changed_source_rejected_before_output_created(self):
        (self.after/'source.png').write_bytes(b'different')
        with self.assertRaises(ValueError):create(self.before,self.after,self.output)
        self.assertFalse(self.output.exists())
        (self.after/'source.png').write_bytes(b'same source')
        (self.after/'output.png').unlink()
        with self.assertRaises(ValueError):create(self.before,self.after,self.output)
        self.assertFalse(self.output.exists())

    def test_missing_rating_rows_and_invalid_votes_are_rejected(self):
        create(self.before,self.after,self.output)
        path=self.output/'reviewer/ratings.csv'
        path.write_text(','.join(FIELDS)+'\n')
        with self.assertRaises(ValueError):summarize(self.output/'answer-key.json',path)
        path.write_text(','.join(FIELDS)+'\ncase-001,WIN,,,,,\n')
        with self.assertRaises(ValueError):summarize(self.output/'answer-key.json',path)

    def test_no_overwrite_and_seed_is_reproducible(self):
        first=create(self.before,self.after,self.output,91)
        second=create(self.before,self.after,self.root/'second',91)
        self.assertEqual(first,second)
        with self.assertRaises(FileExistsError):create(self.before,self.after,self.output)

    def test_same_case_id_cannot_hide_a_changed_target(self):
        path=self.after/'results.json';data=json.loads(path.read_text())
        data['cases'][0]['target']['width']=200
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'target'):create(self.before,self.after,self.output)
        self.assertFalse(self.output.exists())

    def test_failed_invalid_or_incomplete_runs_cannot_be_anonymized(self):
        path=self.after/'results.json';original=json.loads(path.read_text())
        for status in ('failed','rendered-invalid','unknown',None):
            with self.subTest(status=status):
                data=json.loads(json.dumps(original));data['cases'][0]['status']=status
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'successful'):create(self.before,self.after,self.output)
                self.assertFalse(self.output.exists())

    def test_supported_success_statuses_keep_visual_warnings(self):
        for status in ('rendered-valid','checks-passed','review'):
            path=self.after/'results.json';data=json.loads(path.read_text())
            data['cases'][0].update(status=status,flags=['Tiny text'])
            path.write_text(json.dumps(data))
            self.assertEqual(1,len(create(self.before,self.after,self.root/status)))

    def test_missing_or_malformed_targets_fail_before_creating_pack(self):
        for target in (None,{},dict(width=0,height=100),dict(width=True,height=100),
                       dict(width=1.5,height=100),dict(width=float('inf'),height=100)):
            path=self.after/'results.json';data=json.loads(path.read_text())
            data['cases'][0]['target']=target;path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'target'):create(self.before,self.after,self.output)
            self.assertFalse(self.output.exists())

    def test_integral_float_targets_compare_with_and_without_explicit_ids(self):
        for explicit_id in (True, False):
            for folder, width in ((self.before,100),(self.after,100.0)):
                path=folder/'results.json';data=json.loads(path.read_text())
                data['cases'][0]['target']['width']=width
                if not explicit_id:data['cases'][0].pop('id',None)
                path.write_text(json.dumps(data))
            output=self.root/('explicit' if explicit_id else 'derived')
            self.assertEqual(1,len(create(self.before,self.after,output)))

    def test_success_label_cannot_hide_recorded_contract_or_source_errors(self):
        path=self.after/'results.json';original=json.loads(path.read_text())
        for error in ({'source_error':'source preview failed'}, {'valid':False},
                      {'errors':['missing ID']}, {'validation_errors':['changed content']}):
            with self.subTest(error=error):
                data=json.loads(json.dumps(original));data['cases'][0].update(error)
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,'successful'):create(self.before,self.after,self.output)
                self.assertFalse(self.output.exists())
