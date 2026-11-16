"""Independently audit actionPlayId against opportunity feature cutoffs."""
import json

import pandas as pd

from scripts.artifact_runs import StagedRun
from scripts.pipeline_validation import current_environment, require, sha256_file, verify_hash
from scripts.recorded_attempt_baseline import ROOT


def linked_pitch_order(events, action):
    """Resolve only explicit unique pitch links; never infer from proximity."""
    link = action.get('actionPlayId')
    if not link:
        return None
    matches = [order for order, event in enumerate(events)
               if event.get('isPitch') and event.get('playId') == link]
    require(len(matches) <= 1, 'Duplicate linked pitch identifier')
    return matches[0] if matches else None


def main():
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    parent = ROOT / 'results/chronology_repair/repaired_provenance.json'
    expected = json.loads(parent.read_text())['repaired_input_hashes']
    stage = StagedRun(ROOT / 'results/action_pitch_link_audit',
                      ROOT / 'data/processed/action_pitch_link_audit')
    provenance = {'environment': current_environment(), 'inputs': {}, 'feeds': {},
                  'script_sha256': sha256_file(__file__)}
    rows = []
    for year in (2022, 2023, 2024):
        path = ROOT / f'data/processed/chronology_repair/opportunities_{year}.csv.gz'
        provenance['inputs'][str(year)] = verify_hash(path, expected[str(year)])
        frame = pd.read_csv(path, low_memory=False)
        attempts = frame[frame.recorded_steal_attempt_indicator]
        for game_pk, group in attempts.groupby('game_pk'):
            require(group.source_sha256.nunique() == 1 and group.source_cache_path.nunique() == 1,
                    'Inconsistent game source')
            feed_path = ROOT / group.source_cache_path.iloc[0]
            provenance['feeds'][str(game_pk)] = verify_hash(feed_path, group.source_sha256.iloc[0])
            feed = json.loads(feed_path.read_bytes())
            plays = {p['about']['atBatIndex']: p for p in feed['liveData']['plays']['allPlays']}
            for row in group.itertuples(index=False):
                events = plays[row.at_bat_index]['playEvents']
                found = 0
                for action_id in row.response_action_ids.split('|'):
                    parts = action_id.split('-')
                    require(parts[0] == 'A' and int(parts[1]) == game_pk
                            and int(parts[2]) == row.at_bat_index, 'Unexpected action key')
                    event_index = int(parts[3])
                    matches = [e for e in events if e['index'] == event_index]
                    require(len(matches) == 1, 'Action event missing or duplicated')
                    action = matches[0]
                    kind = action.get('details', {}).get('eventType', '')
                    if not kind.startswith(('stolen_base_', 'caught_stealing_')):
                        continue
                    found += 1
                    order = linked_pitch_order(events, action)
                    status = ('no_explicit_pitch_link' if order is None else
                              'linked_at_or_before_cutoff' if order <= row.feature_cutoff_event_order
                              else 'linked_after_cutoff')
                    rows.append(dict(season=year, game_pk=game_pk, opportunity_id=row.opportunity_id,
                                     action_id=action_id, event_type=kind, status=status,
                                     cutoff_order=row.feature_cutoff_event_order, linked_pitch_order=order,
                                     action_play_id=action.get('actionPlayId')))
                require(found == row.recorded_steal_attempt_record_count,
                        'Explicit event audit does not cover every attempt record')
        print(f'{year}: audited {len(attempts)} attempt windows', flush=True)
    details = pd.DataFrame(rows)
    require(details.opportunity_id.is_unique, 'Multiple attempt records require separate accounting')
    summary = details.groupby(['season', 'status']).size().rename('attempt_windows').reset_index()
    summary.to_csv(stage.paths.results / 'summary.csv', index=False)
    details.to_csv(stage.paths.local / 'links.csv.gz', index=False)
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        result = pd.read_csv(paths.results / 'summary.csv')
        audit = pd.read_csv(paths.local / 'links.csv.gz')
        require(result.attempt_windows.sum() == len(audit), 'Incomplete link audit')
        require(set(result.season) == {2022, 2023, 2024}, 'Missing season')

    paths = stage.publish(validate)
    print(summary.to_string(index=False))
    print(paths.results)


if __name__ == '__main__':
    main()
