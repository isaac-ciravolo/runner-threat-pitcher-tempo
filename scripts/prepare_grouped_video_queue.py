"""Freeze a G3 video-review sample, including recovered movement evidence."""
import json

import pandas as pd

from scripts.artifact_runs import StagedRun, resolve_run
from scripts.pipeline_validation import require, sha256_file
from scripts.recorded_attempt_baseline import ROOT


def main():
    parent = resolve_run(ROOT / 'results/grouped_histories', ROOT / 'data/processed/grouped_histories')
    frames = [pd.read_csv(parent.local / f'opportunities_{year}.csv.gz', low_memory=False) for year in (2023, 2024)]
    data = pd.concat(frames, ignore_index=True)
    require(data.opportunity_id.str.startswith('G3-').all(), 'G3 source required')
    data['action_interruption'] = data.recorded_action_record_count.gt(0)
    data['movement_evidence_action'] = data.response_action_ids.fillna('').str.contains(r'-m(?:e|r\d+|s\d+)(?:\||$)', regex=True)
    axes = ['season', 'recorded_pitcher_pickoff_indicator', 'recorded_catcher_pickoff_indicator',
            'recorded_unknown_pickoff_indicator', 'terminal_window', 'open_timing',
            'action_interruption', 'movement_evidence_action']
    data['stratum'] = data[axes].astype(str).agg('|'.join, axis=1)
    selected = []
    for stratum, group in data.groupby('stratum', sort=True):
        sample = group.sample(n=min(5, len(group)), random_state=20261115).copy()
        sample['stratum_population'] = len(group)
        sample['stratum_selected'] = len(sample)
        sample['inclusion_probability'] = len(sample) / len(group)
        selected.append(sample)
    queue = pd.concat(selected, ignore_index=True)
    columns = ['opportunity_id', 'game_pk', 'season', 'at_bat_index', 'inning', 'half_inning',
               'pitcher_id', 'runner_id', 'open_timing', 'open_anchor', 'close_event_index',
               'feature_cutoff_game_sequence', 'terminal_window', 'recorded_pitcher_pickoff_indicator',
               'recorded_catcher_pickoff_indicator', 'recorded_unknown_pickoff_indicator',
               'action_interruption', 'movement_evidence_action', 'stratum', 'stratum_population',
               'stratum_selected', 'inclusion_probability']
    queue = queue[columns]
    queue['review_status'] = 'unreviewed'
    for column in ['video_url', 'reviewer', 'observed_pitcher_pickoff', 'continuity_verified', 'notes']:
        queue[column] = ''
    stage = StagedRun(ROOT / 'results/grouped_video_queue', ROOT / 'data/processed/grouped_video_queue')
    queue.to_csv(stage.paths.results / 'review_queue.csv', index=False)
    blinded_columns = ['opportunity_id', 'game_pk', 'season', 'at_bat_index', 'inning', 'half_inning',
                       'pitcher_id', 'runner_id', 'open_timing', 'open_anchor', 'close_event_index',
                       'review_status', 'video_url', 'reviewer', 'observed_pitcher_pickoff',
                       'continuity_verified', 'notes']
    queue[blinded_columns].to_csv(stage.paths.results / 'annotation_sheet.csv', index=False)
    population = data.groupby('stratum').size().rename('population').reset_index()
    population.to_csv(stage.paths.local / 'stratum_population.csv', index=False)
    provenance = dict(parent_manifest_sha256=sha256_file(parent.results / 'manifest.json'),
                      script_sha256=sha256_file(__file__), seed=20261115, strata=axes,
                      selected=len(queue), population=len(data), genuine_annotations=0)
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        saved = pd.read_csv(paths.results / 'review_queue.csv')
        require(saved.opportunity_id.is_unique and saved.review_status.eq('unreviewed').all(), 'Queue integrity')
        require(saved.inclusion_probability.gt(0).all() and saved.inclusion_probability.le(1).all(), 'Sampling probability')
        require(saved.drop_duplicates('stratum').stratum_population.sum() == len(data), 'Stratum coverage')
        require(saved.groupby('stratum').size().eq(saved.groupby('stratum').stratum_selected.first()).all(), 'Sample counts')
        blinded = pd.read_csv(paths.results / 'annotation_sheet.csv')
        require(set(blinded.opportunity_id) == set(saved.opportunity_id), 'Blinded sample mismatch')
        require(not any(column.startswith('recorded_') for column in blinded.columns)
                and 'stratum' not in blinded and 'movement_evidence_action' not in blinded,
                'Expected outcomes leaked into annotation sheet')

    result = stage.publish(validate)
    print(f'Prepared {len(queue)} unreviewed windows in {queue.stratum.nunique()} strata')
    print(result.results)


if __name__ == '__main__':
    main()
