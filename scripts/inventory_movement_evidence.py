"""Inventory action evidence omitted by the standalone-event classifier."""
import json

import pandas as pd

from scripts.artifact_runs import StagedRun
from scripts.movement_evidence import movement_evidence
from scripts.pipeline_validation import require, verify_hash, sha256_file, current_environment
from scripts.recorded_attempt_baseline import ROOT
from scripts.runner_control_audit import _mapping_for_event


def main():
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    manifests = pd.concat([pd.read_csv(ROOT / f'data/historical_feed_manifest_{year}.csv')
                           for year in (2022, 2023, 2024)], ignore_index=True)
    manifests = manifests[manifests.feed_eligible.eq(True)]
    stage = StagedRun(ROOT / 'results/movement_evidence_inventory', ROOT / 'data/processed/movement_evidence_inventory')
    records = []
    for index, row in enumerate(manifests.itertuples(index=False), 1):
        path = ROOT / row.cache_path
        verify_hash(path, row.sha256)
        feed = json.loads(path.read_bytes())
        for play in feed['liveData']['plays']['allPlays']:
            movements = {}
            for item in play.get('runners', []):
                movements.setdefault(item.get('details', {}).get('playIndex'), []).append(item)
            for event in play.get('playEvents', []):
                if _mapping_for_event(event)[0] is not None:
                    continue
                kinds, paths = movement_evidence(movements.get(event['index'], []))
                if kinds:
                    records.append(dict(game_pk=row.game_pk, season=row.season,
                                        at_bat_index=play['about']['atBatIndex'], event_index=event['index'],
                                        record_type=event.get('type'), is_pitch=event.get('isPitch', False),
                                        action_types='|'.join(sorted(kinds)),
                                        actors=len({item['details']['runner']['id'] for item in paths})))
        if index % 1000 == 0:
            print(f'Inventoried movement evidence in {index}/7289 games', flush=True)
    table = pd.DataFrame(records)
    table.to_csv(stage.paths.local / 'candidates.csv.gz', index=False)
    table.groupby(['season', 'record_type', 'is_pitch', 'action_types']).agg(
        records=('game_pk', 'size'), games=('game_pk', 'nunique')).to_csv(stage.paths.results / 'summary.csv')
    table[table.action_types.str.contains('|', regex=False)].to_csv(stage.paths.results / 'mixed_classes.csv', index=False)
    manifests[['game_pk', 'season', 'sha256']].to_csv(stage.paths.results / 'source_hashes.csv', index=False)
    provenance = dict(environment=current_environment(), script_sha256=sha256_file(__file__),
                      helper_sha256=sha256_file(ROOT / 'scripts/movement_evidence.py'), games=len(manifests),
                      classifier_sha256=sha256_file(ROOT / 'scripts/runner_control_audit.py'))
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        saved = pd.read_csv(paths.local / 'candidates.csv.gz')
        require(not saved[['game_pk', 'at_bat_index', 'event_index']].duplicated().any(), 'Duplicate candidates')
        require(len(manifests) == 7289, 'Incomplete source coverage')

    result = stage.publish(validate)
    print(pd.read_csv(result.results / 'summary.csv').to_string(index=False))
    print(result.results)


if __name__ == '__main__':
    main()
