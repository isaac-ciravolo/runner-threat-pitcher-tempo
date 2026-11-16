import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.artifact_runs import RunPaths
from scripts.pipeline_validation import ValidationError
from scripts import pitcher_response, recorded_attempt_baseline


class GroupedModelHandoffTests(unittest.TestCase):
    def test_matching_keys_do_not_allow_stale_threat_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'provenance.json').write_text(json.dumps({'hashes': {'2023': 'old', '2024': 'old'}}))
            with patch.object(pitcher_response, 'ROOT', root), \
                    patch.object(pitcher_response, 'resolve_run', return_value=RunPaths(root, root)), \
                    patch.object(pitcher_response, 'fit') as fit:
                with self.assertRaisesRegex(ValidationError, 'different opportunity snapshot'):
                    pitcher_response.main(input_dir=root, verified_hashes={'2023': 'new', '2024': 'new'})
                fit.assert_not_called()

    def test_baseline_requires_paired_artifact_roots(self):
        with self.assertRaisesRegex(ValidationError, 'both result and local'):
            recorded_attempt_baseline.main(output_dir='unused')

    def test_baseline_rejects_stale_data_before_fitting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'docs').mkdir()
            (root / 'docs/recorded_attempt_baseline_spec.md').write_text('frozen')
            inputs = root / 'inputs'
            inputs.mkdir()
            (inputs / 'opportunities_2022.csv.gz').write_bytes(b'changed')
            with patch.object(recorded_attempt_baseline, 'ROOT', root), \
                    patch.object(recorded_attempt_baseline, 'fit') as fit:
                with self.assertRaisesRegex(ValidationError, 'checksum mismatch'):
                    recorded_attempt_baseline.main(input_dir=inputs, output_dir=root / 'results',
                                                   local_dir=root / 'local', verified_hashes={'2022': 'old'})
                fit.assert_not_called()
                self.assertFalse((root / 'results/current_run.json').exists())
