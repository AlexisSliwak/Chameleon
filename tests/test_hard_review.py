import copy
import json
from pathlib import Path
import sys
import time
import tempfile
import unittest
from unittest.mock import patch

from scripts.review_hard_cases import (load_suite, preservation_errors, quality_flags,
                                       execute, evaluate_case)
from scripts.review_gallery import write_gallery

ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT/'tests/fixtures/hard-challenges'


class HardFixtureTests(unittest.TestCase):
    def test_all_sources_valid_with_measured_copy_and_only_expected_missing_asset(self):
        from engine.validation import validate_source, validate_target
        from engine.measure import TextMeasurer
        suite,families = load_suite(SUITE)
        self.assertEqual(7,len(families))
        self.assertEqual(28,sum(len(f['targets']) for f,t in families))
        self.assertGreaterEqual(max(len(t['source']['elements']) for f,t in families),30)
        measurer = TextMeasurer()
        for family,task in families:
            with self.subTest(fixture=family['file']):
                self.assertFalse(validate_source(task['source']))
                for target in family['targets']:
                    self.assertFalse(validate_target(target['canvas']))
                missing = {e['asset_id'] for e in task['source']['elements'] if e['type']=='image' and not (ROOT/'brand_kit/assets'/e['asset_id']).is_file()}
                self.assertEqual(set(family['expected_missing_assets']),missing)
                for e in task['source']['elements']:
                    if e['type']=='text':
                        extent=measurer.measure(e)
                        self.assertTrue(extent.fits(e['width'],e['height']),e['id'])
                        self.assertEqual(0,extent.missing_glyphs,e['id'])

    def test_official_reference_is_unchanged(self):
        self.assertEqual((ROOT/'input/chameleon_sample_level3_advanced.json').read_bytes(),
                         (SUITE/'official-advanced.json').read_bytes())

    def test_suite_rejects_path_escape_and_duplicate_targets(self):
        suite=json.loads((SUITE/'suite.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for invalid in ('../secret.json','/absolute.json'):
                altered=copy.deepcopy(suite);altered['families'][0]['file']=invalid
                (folder/'suite.json').write_text(json.dumps(altered))
                with self.assertRaises(ValueError):load_suite(folder)
            altered=copy.deepcopy(suite);altered['families']=altered['families'][:1]
            altered['families'][0]['targets']*=2
            (folder/'suite.json').write_text(json.dumps(altered))
            (folder/'official-advanced.json').write_bytes((SUITE/'official-advanced.json').read_bytes())
            with self.assertRaises(ValueError):load_suite(folder)


class ReviewHarnessTests(unittest.TestCase):
    def setUp(self):
        self.task=json.loads((SUITE/'typography-pressure.json').read_text())

    def test_preservation_allows_geometry_but_detects_copy_style_and_duplicate_changes(self):
        source=self.task['source']; target=source['canvas']; output=copy.deepcopy(source)
        output['elements'][1]['font_size']=30
        self.assertEqual([],preservation_errors(source,target,output))
        output['elements'][1]['content']='Rewritten'
        self.assertTrue(preservation_errors(source,target,output))
        output=copy.deepcopy(source);output['elements'][1]['color']='rgba(0,0,0,1)'
        self.assertTrue(preservation_errors(source,target,output))
        output=copy.deepcopy(source);output['elements'][-1]=output['elements'][0]
        self.assertTrue(preservation_errors(source,target,output))

    def test_readability_warnings_are_not_preservation_errors(self):
        flags=quality_flags(dict(minimum_font_size=5,raster=dict(low_contrast_proxy=.4),missing_glyphs=1))
        self.assertIn('Very small type: below 8px',flags)
        self.assertIn('Missing font glyphs',flags)
        self.assertIn('Possible low contrast',flags)
        self.assertEqual([],quality_flags(dict(minimum_font_size=20)))
        self.assertIn('Possible low contrast',quality_flags(dict(minimum_font_size=24,
                      raster=dict(low_contrast_proxy=0,sampled_low_contrast_proxy=.4))))

    def test_timeout_retains_partial_output(self):
        result=execute([sys.executable,'-c',"import time;print('started',flush=True);time.sleep(10)"],.2,ROOT)
        self.assertTrue(result['timed_out'])
        self.assertIn('started',result['stdout'])

    def test_timeout_stops_child_processes_and_later_cases_still_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker=Path(temporary)/'child-finished'
            child="import time,pathlib;time.sleep(1);pathlib.Path("+repr(str(marker))+").write_text('leaked')"
            parent="import subprocess,sys,time;p=subprocess.Popen([sys.executable,'-c',"+repr(child)+"]);print('child started',flush=True);time.sleep(10)"
            result=execute([sys.executable,'-c',parent],.3,ROOT)
            self.assertTrue(result['timed_out'])
            self.assertIn('child started',result['stdout'])
            time.sleep(1.2)
            self.assertFalse(marker.exists(),'timed-out child kept executing')
            following=execute([sys.executable,'-c',"print('next case')"],2,ROOT)
            self.assertEqual(0,following['returncode'])
            self.assertFalse(following['timed_out'])
            self.assertIn('next case',following['stdout'])

    def test_launch_failure_is_recorded(self):
        result=execute(['/definitely/missing/chameleon-command'],1,ROOT)
        self.assertIsNone(result['returncode'])
        self.assertIn('FileNotFoundError',result['stderr'])

    def test_failed_case_and_logs_are_retained(self):
        family=load_suite(SUITE)[1][0][0]
        task=json.loads((SUITE/family['file']).read_text())
        result=dict(returncode=2,stdout='',stderr='fixture failure',timed_out=False,seconds=.1)
        with tempfile.TemporaryDirectory() as temp,patch('scripts.review_hard_cases.execute',return_value=result):
            row=evaluate_case(family,task,family['targets'][0],Path(temp),1,ROOT/'brand_kit/assets',ROOT/'brand_kit/fonts')
            self.assertEqual('failed',row['status'])
            self.assertTrue(row['errors'])
            self.assertEqual('fixture failure',(Path(temp)/row['log']).read_text())
            self.assertTrue((Path(temp)/'cases'/row['id']/'result.json').is_file())

    def test_gallery_retains_failure_and_escapes_untrusted_labels(self):
        malicious='</script><img src=x onerror=alert(1)>'
        row=dict(id='failure',family=malicious,fixture='f.json',target_name='tiny',pressure='extreme',
                 target=dict(width=90,height=30),source_canvas=dict(width=400,height=400),
                 source_png='sources/f.png',source_error='Missing source',element_count=3,
                 execution=dict(seconds=1),status='failed',tags=[malicious],review=[malicious],
                 errors=['runner failed'],flags=[],warnings=[],log='stderr.log')
        manifest=dict(suite=dict(families=[dict(name=malicious)]))
        with tempfile.TemporaryDirectory() as temp:
            write_gallery(Path(temp),manifest,[row],'frozen-run')
            content=(Path(temp)/'index.html').read_text()
            self.assertNotIn(malicious,content)
            self.assertIn('No usable PNG',content)
            self.assertIn('Source render failed',content)
            self.assertIn('value="unreviewed"',content)
            self.assertTrue((Path(temp)/'review.js').is_file())

    def test_output_pair_checks_detect_mutation_wrong_pixels_and_changed_copy(self):
        from PIL import Image
        family,task=load_suite(SUITE)[1][1]
        target=family['targets'][0]
        for defect in ('none','input-mutation','wrong-dimensions','not-png','changed-copy'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as temp:
                def runner(command,timeout,cwd):
                    folder=Path(command[command.index('--output-dir')+1]);folder.mkdir()
                    design=copy.deepcopy(task['source'])
                    if defect=='changed-copy':
                        next(e for e in design['elements'] if e['type']=='text')['content']='Lost original copy'
                    (folder/'task_output.json').write_text(json.dumps(design))
                    size=(1,1) if defect=='wrong-dimensions' else tuple(target['canvas'][k] for k in ('width','height'))
                    Image.new('RGB',size).save(folder/'task_output.png',format='JPEG' if defect=='not-png' else 'PNG')
                    if defect=='input-mutation':
                        (Path(command[command.index('--input-dir')+1])/'task.json').write_text('{}')
                    return dict(returncode=0,stdout='',stderr='',timed_out=False,seconds=.1)
                with patch('scripts.review_hard_cases.execute',side_effect=runner):
                    row=evaluate_case(family,task,target,Path(temp),1,ROOT/'brand_kit/assets',ROOT/'brand_kit/fonts')
                if defect=='none':
                    self.assertEqual('checks-passed',row['status'])
                    self.assertFalse(row['errors'])
                else:
                    self.assertEqual('failed',row['status'])
                    self.assertTrue(row['errors'])
                self.assertTrue((Path(temp)/'cases'/row['id']/'result.json').exists())


class GalleryProvenanceTests(unittest.TestCase):
    def test_gallery_uses_actual_suite_counts_and_escaped_provenance(self):
        manifest=dict(suite=dict(families=[dict(name='Only family')],provenance='<private> synthetic suite'))
        with tempfile.TemporaryDirectory() as temp:
            write_gallery(Path(temp),manifest,[],'provenance-test')
            page=(Path(temp)/'index.html').read_text()
            self.assertIn('Source families: 1',page)
            self.assertIn('Cases: 0',page)
            self.assertIn('&lt;private&gt; synthetic suite',page)
            self.assertNotIn('Six authored stress families',page)
            self.assertNotIn('<private>',page)


if __name__=='__main__':
    unittest.main()
