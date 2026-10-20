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
            (folder/'results.json').write_text(json.dumps(dict(cases=[dict(id='family--target',fixture='family.json',png='output.png',json='output.json',source_png='source.png')])))
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
