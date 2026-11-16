"""Compare G3 attempt outcomes with source credit reasons; do not fit success."""
import json

import pandas as pd

from scripts.artifact_runs import StagedRun, resolve_run
from scripts.conditional_success_audit import classify
from scripts.pipeline_validation import require, sha256_file, verify_hash
from scripts.recorded_attempt_baseline import ROOT
from scripts.scoring_credit_audit import SB_TAGS, CS_TAGS


def main():
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    source = resolve_run(ROOT / 'results/grouped_histories', ROOT / 'data/processed/grouped_histories')
    rows, flow = [], []
    for year in (2022, 2023, 2024):
        data = pd.read_csv(source.local / f'opportunities_{year}.csv.gz', low_memory=False)
        dispositions = classify(data)
        attempts = data[data.recorded_steal_attempt_indicator]
        flow.append(dict(season=year, windows=len(data), attempt_windows=len(attempts),
                         attempt_records=int(data.recorded_steal_attempt_record_count.sum()),
                         attribution_excluded=int(dispositions.eq('binary_attribution_excluded').sum()),
                         unresolved_or_multiple=int(dispositions.eq('unresolved_or_multiple').sum())))
        for game, group in attempts.groupby('game_pk'):
            first = group.iloc[0]
            path = ROOT / first.source_cache_path
            verify_hash(path, first.source_sha256)
            feed = json.loads(path.read_bytes())
            plays = {play['about']['atBatIndex']: play for play in feed['liveData']['plays']['allPlays']}
            for row in group.itertuples(index=False):
                indexes = {int(action.split('-')[3]) for action in row.response_action_ids.split('|')}
                movements = [item for item in plays[row.at_bat_index].get('runners', [])
                             if item.get('details', {}).get('playIndex') in indexes
                             and item.get('details', {}).get('runner', {}).get('id') == row.runner_id]
                reasons = {item.get('details', {}).get('movementReason') for item in movements}
                sb = bool(reasons & {'r_' + tag for tag in SB_TAGS})
                cs = bool(reasons & {'r_' + tag for tag in CS_TAGS})
                rows.append(dict(opportunity_id=row.opportunity_id, season=year, game_pk=game,
                                 at_bat_index=row.at_bat_index, runner_id=row.runner_id,
                                 parser_outcome=row.recorded_steal_outcome_class,
                                 attribution_eligible=row.attempt_history_eligible,
                                 recorded_attempt_records=row.recorded_steal_attempt_record_count,
                                 opening_runner_sb_reason=sb, opening_runner_cs_reason=cs,
                                 attempt_path_has_out=any(item.get('movement', {}).get('isOut', False) for item in movements),
                                 movement_reasons='|'.join(sorted(reason for reason in reasons if reason)),
                                 response_action_ids=row.response_action_ids,
                                 source_cache_path=row.source_cache_path, source_sha256=row.source_sha256))
        print(f'Audited G3 source outcomes for {year}', flush=True)
    review = pd.DataFrame(rows)
    stage = StagedRun(ROOT / 'results/grouped_success_audit', ROOT / 'data/processed/grouped_success_audit')
    pd.DataFrame(flow).to_csv(stage.paths.results / 'sample_flow.csv', index=False)
    axes = ['season', 'parser_outcome', 'attribution_eligible', 'opening_runner_sb_reason',
            'opening_runner_cs_reason', 'attempt_path_has_out']
    review.groupby(axes).size().rename('windows').reset_index().to_csv(stage.paths.results / 'outcome_crosswalk.csv', index=False)
    review.to_csv(stage.paths.local / 'source_review.csv.gz', index=False)
    exceptions = review[review.attribution_eligible & (
        review.opening_runner_sb_reason.eq(review.opening_runner_cs_reason)
        | review.recorded_attempt_records.ne(1)
        | (review.opening_runner_sb_reason & review.attempt_path_has_out)
        | (review.parser_outcome.eq('recorded_success') & review.opening_runner_cs_reason)
        | (review.parser_outcome.eq('recorded_unsuccessful') & review.opening_runner_sb_reason))]
    exceptions.to_csv(stage.paths.results / 'review_exceptions.csv', index=False)
    provenance = dict(parent_manifest_sha256=sha256_file(source.results / 'manifest.json'),
                      script_sha256=sha256_file(__file__), fitting_performed=False,
                      protocol_sha256=sha256_file(ROOT / 'docs/grouped_success_review_protocol.md'),
                      helper_sha256={name: sha256_file(ROOT / 'scripts' / name) for name in
                                     ['conditional_success_audit.py', 'scoring_credit_audit.py']},
                      interpretation='source credit reasons for the opening runner; path out is not a full closure-state label')
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        saved = pd.read_csv(paths.local / 'source_review.csv.gz')
        require(saved.opportunity_id.is_unique and len(saved) == sum(row['attempt_windows'] for row in flow),
                'Attempt review accounting mismatch')
        require(pd.read_csv(paths.results / 'outcome_crosswalk.csv').windows.sum() == len(saved), 'Outcome crosswalk mismatch')

    completed = stage.publish(validate)
    print(pd.DataFrame(flow).to_string(index=False))
    print('Target-definition review cases:', len(exceptions))
    print(completed.results)


if __name__ == '__main__':
    main()
