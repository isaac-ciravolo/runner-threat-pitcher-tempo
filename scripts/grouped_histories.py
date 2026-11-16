"""Rebuild and independently verify histories after completed-play reconstruction."""
import json

import pandas as pd

from scripts.artifact_runs import StagedRun, resolve_run
from scripts.historical_processing import ForwardHistoryState
from scripts.opening_identities import repair_opening_identities
from scripts.pipeline_validation import current_environment, require, sha256_file, verify_hash
from scripts.recorded_attempt_baseline import ROOT
from scripts.source_snapshot import validate_source_snapshot
from scripts.verify_response_boundaries import verify_response_boundaries

SUFFIXES = {'eligible_opportunities': ('opportunity_id', 'size'),
            'attempted_opportunities': ('recorded_steal_attempt_indicator', 'sum'),
            'attempt_records': ('recorded_steal_attempt_record_count', 'sum'),
            'successes': ('recorded_steal_success_count', 'sum'),
            'unsuccessful': ('recorded_steal_unsuccessful_count', 'sum'),
            'ambiguous_outcomes': ('recorded_steal_ambiguous_count', 'sum')}


def verify_histories(data, timing, selected):
    """Compare incremental history to independent sums over completed games."""
    eligible = data[data.attempt_history_eligible].copy()
    eligible['available'] = eligible.game_pk.map(timing.available)
    checked = 0
    for game_pk in sorted(selected):
        current = data[data.game_pk.eq(game_pk)].drop_duplicates('runner_id')
        prior = eligible[eligible.available.lt(timing.loc[game_pk, 'freeze'])]
        require(not prior.game_pk.eq(game_pk).any(), 'Current game entered history')
        for era, subset in [('all_regimes', prior), ('pre_2023', prior[prior.season.eq(2022)]),
                            ('post_2023', prior[prior.season.ge(2023)])]:
            expected = subset.groupby('runner_id').agg(**SUFFIXES)
            for row in current.itertuples(index=False):
                for suffix in SUFFIXES:
                    value = expected.loc[row.runner_id, suffix] if row.runner_id in expected.index else 0
                    require(getattr(row, f'runner_prior_{era}_{suffix}') == value,
                            f'History mismatch: {game_pk}/{row.runner_id}/{era}/{suffix}')
                    checked += 1
    return checked


def main():
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    rebuilt = resolve_run(ROOT / 'results/grouped_event_rebuild', ROOT / 'data/processed/grouped_event_rebuild')
    metadata = pd.read_csv(rebuilt.results / 'games.csv')
    require(len(metadata) == 7289 and metadata.game_pk.is_unique, 'Incomplete full rebuild')
    require(metadata.parser_version.eq('historical_processing_v3_movement').all(), 'Movement completion required before histories')
    audit_path = ROOT / 'results/chronology_repair/game_chronology_audit.csv'
    timing_path = ROOT / 'results/chronology_repair/timing_dispositions.csv'
    audit = pd.read_csv(audit_path)
    timing = pd.read_csv(timing_path).set_index('game_pk')
    require(timing.status.eq('resolved').all(), 'Unresolved between-game timing')
    timing['freeze'] = pd.to_datetime(timing.freeze_time, utc=True, format='mixed')
    timing['available'] = pd.to_datetime(timing.available_after, utc=True, format='mixed')
    require(timing.freeze.lt(timing.available).all(), 'Invalid game availability')
    identity_audit = resolve_run(ROOT / 'results/opening_identity_audit', ROOT / 'data/processed/opening_identity_audit')
    require(pd.read_csv(identity_audit.results / 'exceptions.csv').empty, 'Unresolved pitcher identities')
    identity_sources = pd.read_csv(identity_audit.results / 'games.csv').set_index('game_pk')
    frames, identity_changes, boundary_checks = [], [], []
    for row in metadata.itertuples(index=False):
        path = ROOT / row.output_path
        verify_hash(path, row.output_sha256)
        frame = pd.read_csv(path, low_memory=False)
        require(identity_sources.loc[row.game_pk, 'sha256'] == row.feed_sha256, 'Identity source mismatch')
        feed_path = ROOT / row.feed_cache_path
        verify_hash(feed_path, row.feed_sha256)
        feed = json.loads(feed_path.read_bytes())
        boundary_checks.append(dict(game_pk=row.game_pk, season=row.season,
                                    **verify_response_boundaries(frame, feed)))
        fixed, changed = repair_opening_identities(frame, feed)
        identity_changes.append(dict(game_pk=row.game_pk, season=row.season, changed_pitcher_rows=changed,
                                     prior_history_eligible=int(frame.attempt_history_eligible.sum()),
                                     corrected_history_eligible=int(fixed.attempt_history_eligible.sum())))
        frames.append(fixed)
        if len(frames) % 1000 == 0:
            print(f'Verified responses and identities for {len(frames)}/7289 games', flush=True)
    source = pd.concat(frames, ignore_index=True)
    manifests = pd.concat([pd.read_csv(ROOT / f'data/historical_feed_manifest_{year}.csv')
                           for year in (2022, 2023, 2024)], ignore_index=True)
    validate_source_snapshot(source, audit, timing.reset_index(), manifests[manifests.feed_eligible.eq(True)])
    games = {int(key): frame for key, frame in source.groupby('game_pk', sort=False)}
    state, finished = ForwardHistoryState(), []
    for index, (game_pk, timing_row) in enumerate(timing.sort_values(['freeze', 'game_pk']).iterrows(), 1):
        frame = games[game_pk].copy()
        state.release_completed_before(timing_row.freeze)
        snapshots = {runner: state.snapshot(runner, coverage_complete=True) for runner in frame.runner_id.unique()}
        histories = pd.DataFrame([snapshots[runner] for runner in frame.runner_id], index=frame.index)
        frame = pd.concat([frame, histories], axis=1)
        frame['legacy_feed_game_start_utc'] = frame.feed_game_start_utc
        frame['legacy_feed_completion_time_utc'] = frame.feed_completion_time_utc
        frame['feed_game_start_utc'] = timing_row.freeze.isoformat()
        frame['history_available_after_utc'] = timing_row.available.isoformat()
        frame['last_observed_event_time_utc'] = timing_row.last_observed_time
        frame['chronology_version'] = 'event_bounds_v2'
        frame['history_frozen_before_game'] = True
        frame['game_chronology_available'] = True
        frame['runner_history_coverage_reason'] = 'complete_grouped_development_with_v2_availability'
        finished.append(frame)
        state.queue_game(season=int(frame.season.iloc[0]), completion_time=timing_row.available, frame=frame)
        if index % 1000 == 0:
            print(f'Built grouped histories for {index}/7289 games', flush=True)
    data = pd.concat(finished, ignore_index=True)
    require(data.opportunity_id.is_unique and data.opportunity_id.str.startswith('G3-').all(), 'Versioned key mismatch')
    for suffix in SUFFIXES:
        require(data[f'runner_prior_all_regimes_{suffix}'].eq(
            data[f'runner_prior_pre_2023_{suffix}'] + data[f'runner_prior_post_2023_{suffix}']).all(), 'Era accounting')
    numeric = [column for column in data if column.startswith('runner_prior_')]
    require(data.groupby(['game_pk', 'runner_id'])[numeric].nunique().le(1).all().all(), 'Within-game history update')
    selected = set(audit[audit.resume_date.notna()].game_pk) | {663178, 663065, 661565, 745520}
    selected.update(pd.Series(timing.index).sample(n=20, random_state=20261115))
    checked = verify_histories(data, timing, selected)
    stage = StagedRun(ROOT / 'results/grouped_histories', ROOT / 'data/processed/grouped_histories')
    hashes = {}
    for year, group in data.groupby('season'):
        path = stage.paths.local / f'opportunities_{year}.csv.gz'
        group.to_csv(path, index=False)
        hashes[str(year)] = sha256_file(path)
    flow = data.groupby('season').agg(windows=('opportunity_id', 'size'), games=('game_pk', 'nunique'),
                                     attempts=('recorded_steal_attempt_indicator', 'sum'),
                                     pitcher_pickoffs=('recorded_pitcher_pickoff_indicator', 'sum'),
                                     terminal=('terminal_window', 'sum'))
    flow.to_csv(stage.paths.results / 'sample_flow.csv')
    pd.DataFrame(identity_changes).to_csv(stage.paths.results / 'identity_changes.csv', index=False)
    pd.DataFrame(boundary_checks).to_csv(stage.paths.results / 'response_boundary_checks.csv', index=False)
    provenance = dict(environment=current_environment(), grouped_input_hashes=hashes,
                      parent_manifest_sha256=sha256_file(rebuilt.results / 'manifest.json'),
                      timing_sha256=sha256_file(timing_path), audit_sha256=sha256_file(audit_path),
                      source_sha256=sha256_file(__file__), rows=len(data),
                      identity_source_sha256=sha256_file(ROOT / 'scripts/opening_identities.py'),
                      boundary_audit_sha256=sha256_file(ROOT / 'scripts/verify_response_boundaries.py'),
                      identity_audit_manifest_sha256=sha256_file(identity_audit.results / 'manifest.json'),
                      independent_history_equalities=checked, independent_games=sorted(selected))
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        for year, expected in hashes.items():
            verify_hash(paths.local / f'opportunities_{year}.csv.gz', expected)
        require(pd.read_csv(paths.results / 'sample_flow.csv').windows.sum() == len(data), 'Flow mismatch')

    paths = stage.publish(validate)
    print(flow.to_string())
    print(f'Independent history checks: {checked}')
    print(paths.results)
    return paths


if __name__ == '__main__':
    main()
