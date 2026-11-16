"""Run unchanged frozen model specifications against verified grouped histories."""
import argparse
import json

from scripts.artifact_runs import resolve_run
from scripts.pipeline_validation import require, sha256_file
from scripts.recorded_attempt_baseline import ROOT


def main(stage):
    histories = resolve_run(ROOT / 'results/grouped_histories', ROOT / 'data/processed/grouped_histories')
    provenance = json.loads((histories.results / 'provenance.json').read_text())
    require(provenance['independent_history_equalities'] > 0, 'Independent history audit required')
    definition = {'event_boundary_version': 'completed_linked_play_v2',
                  'history_availability_field': 'history_available_after_utc',
                  'grouped_history_manifest_sha256': sha256_file(histories.results / 'manifest.json'),
                  'repair_protocol_sha256': sha256_file(ROOT / 'docs/grouped_event_repair_protocol.md'),
                  'implementation_sha256': {name: sha256_file(ROOT / 'scripts' / name) for name in
                                            ['grouped_models.py', 'recorded_attempt_baseline.py',
                                             'forward_threat.py', 'pitcher_response.py']}}
    if stage == 'baseline':
        from scripts.recorded_attempt_baseline import main as run
        return run(input_dir=histories.local, output_dir=ROOT / 'results/recorded_attempt_grouped',
                   local_dir=ROOT / 'data/processed/recorded_attempt_grouped',
                   verified_hashes=provenance['grouped_input_hashes'], use_availability=True,
                   definition_provenance=definition)
    if stage == 'forward':
        from scripts.forward_threat import main as run
        return run(input_dir=histories.local, output_dir=ROOT / 'results/forward_threat_grouped',
                   local_dir=ROOT / 'data/processed/forward_threat_grouped',
                   verified_hashes=provenance['grouped_input_hashes'], use_availability=True,
                   provenance_extra=definition)
    require(stage == 'response', 'Unknown model stage')
    from scripts.pitcher_response import main as run
    return run(input_dir=histories.local, verified_hashes=provenance['grouped_input_hashes'],
               forward_results=ROOT / 'results/forward_threat_grouped',
               forward_local=ROOT / 'data/processed/forward_threat_grouped',
               output_dir=ROOT / 'results/pitcher_response_grouped',
               local_dir=ROOT / 'data/processed/pitcher_response_grouped',
               definition_provenance=definition)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['baseline', 'forward', 'response'])
    main(parser.parse_args().stage)
