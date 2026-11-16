"""Audit the existing success denominator without treating it as validated credit."""
import json

import pandas as pd

from scripts.artifact_runs import StagedRun
from scripts.pipeline_validation import current_environment, require, sha256_file, verify_hash
from scripts.recorded_attempt_baseline import ROOT


def classify(frame):
    """Assign exhaustive, disjoint dispositions; fail on inconsistent counts."""
    attempts = frame.recorded_steal_attempt_record_count
    successes = frame.recorded_steal_success_count
    failures = frame.recorded_steal_unsuccessful_count
    ambiguous = frame.recorded_steal_ambiguous_count
    for counts in (attempts, successes, failures, ambiguous):
        require(counts.notna().all() and counts.ge(0).all()
                and counts.eq(counts.round()).all(), 'Invalid outcome counts')
    require(attempts.eq(successes + failures + ambiguous).all(), 'Outcome accounting mismatch')
    require(frame.recorded_steal_attempt_indicator.eq(attempts.gt(0)).all(), 'Attempt flag mismatch')
    expected = pd.Series('ambiguous_or_multiple', index=frame.index)
    expected.loc[attempts.eq(0)] = 'none'
    expected.loc[attempts.eq(1) & successes.eq(1)] = 'recorded_success'
    expected.loc[attempts.eq(1) & failures.eq(1)] = 'recorded_unsuccessful'
    require(expected.eq(frame.recorded_steal_outcome_class).all(), 'Outcome class mismatch')
    binary = expected.isin(['recorded_success', 'recorded_unsuccessful'])
    require(frame.conditional_success_history_eligible.eq(
        frame.attempt_history_eligible & binary).all(), 'Success eligibility mismatch')
    disposition = pd.Series('not_recorded_attempt', index=frame.index)
    disposition.loc[attempts.gt(0)] = 'unresolved_or_multiple'
    disposition.loc[binary & ~frame.attempt_history_eligible] = 'binary_attribution_excluded'
    disposition.loc[binary & frame.attempt_history_eligible] = 'binary_history_eligible'
    return disposition


def validate(paths):
    flow = pd.read_csv(paths.results / 'sample_flow.csv')
    require(set(flow.season) == {2022, 2023, 2024}, 'Missing audit season')
    require(flow.windows.eq(flow.not_recorded_attempt + flow.attempts).all(), 'Window accounting')
    require(flow.attempts.eq(flow.binary_history_eligible + flow.binary_attribution_excluded
                            + flow.unresolved_or_multiple).all(), 'Attempt accounting')
    review = pd.read_csv(paths.local / 'attempt_review.csv.gz')
    require(review.opportunity_id.is_unique and len(review) == flow.attempts.sum(), 'Review coverage')


def main():
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    provenance_path = ROOT / 'results/chronology_repair/repaired_provenance.json'
    source = json.loads(provenance_path.read_text())
    provenance = {'environment': current_environment(), 'inputs': {},
                  'spec_sha256': sha256_file(ROOT / 'docs/conditional_success_audit_protocol.md'),
                  'source_sha256': sha256_file(__file__),
                  'parent_provenance_sha256': sha256_file(provenance_path)}
    stage = StagedRun(ROOT / 'results/conditional_success_audit',
                      ROOT / 'data/processed/conditional_success_audit')
    rows, reviews = [], []
    for year in (2022, 2023, 2024):
        path = ROOT / f'data/processed/chronology_repair/opportunities_{year}.csv.gz'
        provenance['inputs'][str(year)] = verify_hash(path, source['repaired_input_hashes'][str(year)])
        frame = pd.read_csv(path, low_memory=False)
        require(frame.season.eq(year).all() and frame.opportunity_id.is_unique, 'Season/key mismatch')
        disposition = classify(frame)
        counts = disposition.value_counts()
        attempted = frame.recorded_steal_attempt_indicator
        rows.append(dict(season=year, windows=len(frame), attempts=int(attempted.sum()),
                         terminal_attempts=int((attempted & frame.terminal_window).sum()),
                         recorded_success=int(frame.recorded_steal_outcome_class.eq('recorded_success').sum()),
                         recorded_unsuccessful=int(frame.recorded_steal_outcome_class.eq('recorded_unsuccessful').sum()),
                         **{name: int(counts.get(name, 0)) for name in
                            ['not_recorded_attempt', 'binary_history_eligible',
                             'binary_attribution_excluded', 'unresolved_or_multiple']}))
        columns = ['opportunity_id', 'season', 'game_pk', 'runner_id', 'response_action_ids',
                   'recorded_steal_outcome_class', 'terminal_window',
                   'history_count_exclusion_reason', 'source_cache_path', 'source_sha256']
        review = frame.loc[attempted, columns].copy()
        review['audit_disposition'] = disposition.loc[attempted]
        review['review_status'] = 'unreviewed'
        reviews.append(review)
    pd.DataFrame(rows).to_csv(stage.paths.results / 'sample_flow.csv', index=False)
    pd.concat(reviews, ignore_index=True).to_csv(stage.paths.local / 'attempt_review.csv.gz', index=False)
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    paths = stage.publish(validate)
    print(pd.DataFrame(rows).to_string(index=False))
    print(paths.results)
    return paths


if __name__ == '__main__':
    main()
