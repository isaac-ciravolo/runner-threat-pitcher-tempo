"""Pilot or rebuild grouped opportunities using isolated, checksum-keyed caches."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.artifact_runs import StagedRun, resolve_run
from scripts.historical_processing import build_game_opportunities, atomic_write_gzip_frame
from scripts.pipeline_validation import current_environment, require, sha256_file, verify_hash
from scripts.recorded_attempt_baseline import ROOT

SOURCES = ['scripts/rebuild_grouped_events.py', 'scripts/grouped_events.py',
           'scripts/historical_processing.py', 'scripts/audit_feeds.py',
           'scripts/runner_control_audit.py', 'scripts/prepare_opportunity_dataset.py']


def validate_disengagement_disposition(checks, frame):
    """Allow only the reviewed raw-counter discrepancy outside every risk window."""
    bad = checks[checks.raw_number_available & checks.raw_number_matches.eq(False)]
    require(len(bad) == 1, 'Unreviewed disengagement discrepancy')
    row = bad.iloc[0]
    require(row.action_id == 'A-746241-18-5-e' and row.raw_disengagement_num == 3
            and row.reconstructed_disengagement_num == 1,
            'Unreviewed disengagement discrepancy')
    require(not frame.at_bat_index.eq(18).any(), 'Disengagement discrepancy affects eligible windows')
    return '746241_PA18_no_first_only_window_raw3_reconstructed1'


def audit_disengagement_disposition(row, feed, frame):
    from scripts.historical_processing import parser_manifest_row, source_frame
    from scripts.audit_feeds import extract_events
    from scripts.runner_control_audit import build_action_audit
    from scripts.grouped_events import collapse_outcome_groups
    from scripts.prepare_opportunity_dataset import build_disengagement_history
    loaded = [(parser_manifest_row(row), feed)]
    events, _ = extract_events(loaded)
    actions, _, _ = build_action_audit(loaded, events, source_frame(row))
    events, actions, keys = collapse_outcome_groups(feed, events, actions)
    _, checks = build_disengagement_history(events, actions, loaded, event_key_map=keys)
    return validate_disengagement_disposition(checks, frame)


def process_game(task):
    record, directory = task
    row = pd.Series(record)
    path = ROOT / row.cache_path
    verify_hash(path, row.sha256)
    target = Path(directory) / f'{int(row.game_pk)}.csv.gz'
    marker = target.with_suffix('.json')
    if target.exists() and marker.exists():
        metadata = json.loads(marker.read_text())
        require(metadata['feed_sha256'] == row.sha256, 'Cached source mismatch')
        verify_hash(target, metadata['output_sha256'])
        if metadata['raw_disengagement_mismatches']:
            metadata['disengagement_disposition'] = audit_disengagement_disposition(
                row, json.loads(path.read_bytes()), pd.read_csv(target, low_memory=False))
        return metadata
    feed = json.loads(path.read_bytes())
    frame, metadata = build_game_opportunities(row, feed, group_linked_outcomes=True)
    require(frame.opportunity_id.is_unique, 'Duplicate grouped opportunities')
    require(frame.opening_catcher_id.notna().all(), 'Unresolved opening catcher')
    require(frame.known_state_conflict.eq(False).all(), 'Known state conflict')
    require(frame.unknown_action_classification_count.eq(0).all(), 'Unknown action classification')
    if metadata['raw_disengagement_mismatches']:
        metadata['disengagement_disposition'] = audit_disengagement_disposition(row, feed, frame)
    assigned = [item for value in frame.response_action_ids.dropna() for item in str(value).split('|') if item]
    require(len(assigned) == len(set(assigned)), 'Action assigned to multiple windows')
    metadata['recorded_attempt_windows'] = int(frame.recorded_steal_attempt_indicator.sum())
    metadata['recorded_pitcher_pickoff_windows'] = int(frame.recorded_pitcher_pickoff_indicator.sum())
    metadata['attempts_with_following_pitch'] = int((frame.recorded_steal_attempt_indicator & frame.following_pitch_exists).sum())
    metadata['output_path'] = str(target.relative_to(ROOT))
    atomic_write_gzip_frame(target, frame)
    metadata['output_sha256'] = sha256_file(target)
    marker.write_text(json.dumps(metadata, indent=2) + '\n')
    return metadata


def main(full=False, workers=4):
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    inventory = resolve_run(ROOT / 'results/grouped_event_inventory', ROOT / 'data/processed/grouped_event_inventory')
    manifests = pd.concat([pd.read_csv(ROOT / f'data/historical_feed_manifest_{year}.csv')
                           for year in (2022, 2023, 2024)], ignore_index=True)
    manifests = manifests[manifests.feed_eligible.eq(True)].copy()
    require(manifests.game_pk.is_unique and len(manifests) == 7289, 'Manifest coverage mismatch')
    if not full:
        # Deterministic ordinary games plus every initial exception game.
        initial = ROOT / 'results/grouped_event_inventory/runs/62333b29eb8a46c99df0a015758cc9cd/exceptions.csv'
        selected = set(pd.read_csv(initial).game_pk)
        crosswalk = pd.read_csv(inventory.local / 'crosswalk.csv.gz')
        selected.update(crosswalk.groupby(['season', 'event_type', 'parent_type'], dropna=False).head(1).game_pk)
        selected.update(manifests.sort_values('game_pk').groupby('season').head(4).game_pk)
        selected.update([663178, 716404, 718573, 746241])
        manifests = manifests[manifests.game_pk.isin(selected)]
    hashes = {name: sha256_file(ROOT / name) for name in SOURCES}
    # Selection/report changes do not change parsed rows. Parser dependencies
    # and the cache schema identify reusable outputs; each file is verified.
    cache_definition = {'schema': 1, 'parser_sources': {name: digest for name, digest in hashes.items()
                                                       if name != 'scripts/rebuild_grouped_events.py'}}
    signature = hashlib.sha256(json.dumps(cache_definition, sort_keys=True).encode()).hexdigest()[:16]
    cache = ROOT / 'data/processed/grouped_events/cache' / signature
    cache.mkdir(parents=True, exist_ok=True)
    label = 'grouped_event_rebuild' if full else 'grouped_event_pilot'
    stage = StagedRun(ROOT / 'results' / label, ROOT / 'data/processed' / label)
    tasks = [(row, str(cache)) for row in manifests.to_dict('records')]
    metadata = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for index, result in enumerate(pool.map(process_game, tasks, chunksize=1), 1):
            metadata.append(result)
            if index % 20 == 0:
                print(f'Processed {index}/{len(tasks)} games', flush=True)
    table = pd.DataFrame(metadata)
    table.to_csv(stage.paths.results / 'games.csv', index=False)
    table[['game_pk', 'output_path', 'output_sha256']].to_csv(stage.paths.local / 'cache_index.csv', index=False)
    summary = table.groupby('season')[['opportunities', 'recorded_attempt_windows',
                                      'recorded_pitcher_pickoff_windows', 'terminal_windows',
                                      'attempts_with_following_pitch', 'grouped_outcome_records']].sum()
    summary.to_csv(stage.paths.results / 'summary.csv')
    provenance = dict(environment=current_environment(), source_hashes=hashes, cache_signature=signature,
                      spec_sha256=sha256_file(ROOT / 'docs/grouped_event_repair_protocol.md'),
                      inventory_manifest_sha256=sha256_file(inventory.results / 'manifest.json'),
                      games=len(table), full_development_rebuild=full)
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        saved = pd.read_csv(paths.results / 'games.csv')
        require(set(saved.game_pk) == set(manifests.game_pk), 'Incomplete rebuild')
        for row in saved.itertuples(index=False):
            verify_hash(ROOT / row.output_path, row.output_sha256)

    paths = stage.publish(validate)
    print(summary.to_string())
    print(paths.results)
    return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    require(1 <= args.workers <= 8, 'Use one to eight workers')
    main(full=args.full, workers=args.workers)
