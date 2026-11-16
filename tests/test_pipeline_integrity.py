"""Regression tests for pipeline review findings; never touch research outputs."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from scripts.artifact_runs import StagedRun, RunPaths, resolve_run
from scripts.pipeline_validation import ValidationError, require, current_environment
from scripts.source_snapshot import validate_source_snapshot
from scripts import forward_threat


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.results, self.local = self.root/'results', self.root/'local'

    def stage(self, value):
        run = StagedRun(self.results, self.local)
        (run.paths.results/'table.csv').write_text(value)
        (run.paths.local/'model.bin').write_text(value)
        return run

    @staticmethod
    def validate(paths):
        require((paths.results/'table.csv').read_text() == (paths.local/'model.bin').read_text(),
                'Mismatched staged artifacts')

    def test_success_publishes_both_and_preserves_previous(self):
        old = self.stage('old').publish(self.validate)
        run = self.stage('new')
        self.assertEqual(resolve_run(self.results, self.local), old)
        new = run.publish(self.validate)
        self.assertEqual(resolve_run(self.results, self.local), new)
        self.assertEqual((old.local/'model.bin').read_text(), 'old')

    def test_validation_failure_preserves_pointer(self):
        old = self.stage('old').publish(self.validate)
        pointer = (self.results/'current_run.json').read_bytes()
        bad = self.stage('new')
        (bad.paths.local/'model.bin').write_text('different')
        with self.assertRaises(ValidationError): bad.publish(self.validate)
        self.assertEqual(pointer, (self.results/'current_run.json').read_bytes())
        self.assertEqual(resolve_run(self.results, self.local), old)

    def test_failure_between_directory_moves_preserves_old_run(self):
        old = self.stage('old').publish(self.validate)
        real_replace = os.replace
        calls = 0
        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('simulated interruption')
            return real_replace(source, destination)
        with patch('scripts.artifact_runs.os.replace', side_effect=fail_second):
            with self.assertRaises(OSError): self.stage('new').publish(self.validate)
        self.assertEqual(resolve_run(self.results, self.local), old)

    def test_pointer_failure_does_not_publish_or_fall_back(self):
        old = self.stage('old').publish(self.validate)
        with patch('scripts.artifact_runs._replace_pointer', side_effect=OSError('failure')):
            with self.assertRaises(OSError): self.stage('new').publish(self.validate)
        self.assertEqual(resolve_run(self.results, self.local), old)
        (self.results/'current_run.json').write_text('{invalid')
        with self.assertRaises(json.JSONDecodeError): resolve_run(self.results, self.local)

    def test_tampered_artifact_rejected(self):
        run = self.stage('old').publish(self.validate)
        (run.local/'model.bin').write_text('corrupt')
        with self.assertRaises(ValidationError): resolve_run(self.results, self.local)

    def test_legacy_read_does_not_modify_files(self):
        self.results.mkdir(); self.local.mkdir()
        (self.results/'provenance.json').write_text('{}')
        (self.local/'final_bundle.joblib').write_text('legacy')
        self.assertEqual(resolve_run(self.results, self.local), RunPaths(self.results,self.local))
        self.assertFalse((self.results/'current_run.json').exists())

    def test_first_failed_run_is_not_readable(self):
        self.stage('incomplete')
        with self.assertRaises(ValidationError): resolve_run(self.results, self.local)

    def test_overlapping_roots_rejected(self):
        with self.assertRaises(ValidationError): StagedRun(self.results,self.results/'nested')


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.audit = pd.DataFrame({'game_pk':[1,2], 'season':[2022,2023],
            'source_sha256':['a'*64,'b'*64],
            'freeze_time':['2022-06-01T12:00:00Z','2023-06-01T12:00:00Z'],
            'last_observed_time':['2022-06-01T15:00:00Z','2023-06-01T15:00:00Z']})
        self.dispositions=self.audit.copy()
        self.dispositions['available_after']=self.audit.last_observed_time
        self.manifests=self.audit[['game_pk','source_sha256']].rename(columns={'source_sha256':'sha256'})
        self.rows=pd.DataFrame({'opportunity_id':['1:1','1:2','2:1'], 'game_pk':[1,1,2],
                               'season':[2022,2022,2023], 'source_sha256':['a'*64,'a'*64,'b'*64]})

    def check(self):
        validate_source_snapshot(self.rows,self.audit,self.dispositions,self.manifests)

    def test_matching_snapshot(self): self.check()

    def test_single_stale_opportunity_rejected(self):
        self.rows.loc[1,'source_sha256']='c'*64
        with self.assertRaisesRegex(ValidationError,'Opportunity source snapshot'): self.check()

    def test_refreshed_manifest_rejected(self):
        self.manifests.loc[0,'sha256']='c'*64
        with self.assertRaisesRegex(ValidationError,'manifests: source hashes'): self.check()

    def test_stale_disposition_hash_rejected(self):
        self.dispositions.loc[0,'source_sha256']='c'*64
        with self.assertRaisesRegex(ValidationError,'dispositions: source hashes'): self.check()

    def test_changed_disposition_bound_rejected(self):
        self.dispositions.loc[0,'freeze_time']='2022-06-02T12:00:00Z'
        with self.assertRaisesRegex(ValidationError,'freeze_time differs'): self.check()

    def test_duplicate_audit_rejected(self):
        self.audit=pd.concat([self.audit,self.audit.iloc[[0]]])
        with self.assertRaisesRegex(ValidationError,'unique'): self.check()

    def test_missing_game_rejected(self):
        self.manifests=self.manifests.iloc[:1]
        with self.assertRaisesRegex(ValidationError,'coverage'): self.check()

    def test_early_availability_rejected(self):
        self.dispositions.loc[0,'available_after']='2022-06-01T14:00:00Z'
        with self.assertRaisesRegex(ValidationError,'availability precedes'): self.check()


class RuntimeTests(unittest.TestCase):
    def test_custom_and_failed_invocations_do_not_change_defaults(self):
        defaults=(forward_threat.OUT,forward_threat.LOCAL)
        with patch('scripts.forward_threat.StagedRun') as stage, patch('scripts.forward_threat._execute') as execute:
            stage.return_value.paths=RunPaths(Path('staged-results'),Path('staged-local'))
            forward_threat.main(output_dir=Path('custom'),local_dir=Path('custom-local'))
            execute.side_effect=RuntimeError('failed fit')
            with self.assertRaises(RuntimeError): forward_threat.main(output_dir=Path('failed'))
            execute.side_effect=None
            forward_threat.main()
            self.assertEqual(stage.call_args.args,defaults)
        self.assertEqual((forward_threat.OUT,forward_threat.LOCAL),defaults)

    def test_current_environment_queries_active_versions(self):
        with patch('scripts.pipeline_validation.platform.python_version',return_value='new-python'), patch('scripts.pipeline_validation.version',side_effect=lambda name: 'active-'+name):
            environment=current_environment()
        self.assertEqual(environment, {'python':'new-python','pandas':'active-pandas',
                                      'numpy':'active-numpy','sklearn':'active-scikit-learn'})

    def test_hash_guard_survives_optimized_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'results/recorded_attempt_baseline').mkdir(parents=True)
            (root/'results/recorded_attempt_baseline/provenance.json').write_text(json.dumps({'inputs':{'2022':'wrong'}}))
            (root/'opportunities_2022.csv.gz').write_bytes(b'changed input')
            code=f'''from pathlib import Path
from scripts import forward_threat as f
from scripts.pipeline_validation import ValidationError
f.ROOT=Path({str(root)!r})
try:
    f._execute(input_dir=f.ROOT,output_dir=f.ROOT,local_dir=f.ROOT,verified_hashes=None,use_availability=False,provenance_extra={{}})
except ValidationError as e:
    if 'checksum mismatch' not in str(e): raise
else:
    raise RuntimeError('Optimized execution bypassed the input guard')
'''
            subprocess.run([sys.executable,'-O','-c',code],check=True,capture_output=True,text=True)

    def test_no_optimization_sensitive_runtime_asserts_remain(self):
        for name in ['forward_threat','rebuild_chronology_histories','recorded_attempt_baseline',
                     'chronology_audit','chronology_dispositions','verify_chronology_repair']:
            source=(Path('scripts')/(name+'.py')).read_text(encoding='utf-8')
            self.assertFalse(any(isinstance(node,ast.Assert) for node in ast.walk(ast.parse(source))),name)


if __name__=='__main__': unittest.main()
