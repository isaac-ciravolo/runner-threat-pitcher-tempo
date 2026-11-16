"""Compare unaffected-cache migration with complete source reparsing."""
from concurrent.futures import ProcessPoolExecutor
from io import StringIO
import json

import pandas as pd

from scripts.artifact_runs import resolve_run
from scripts.historical_processing import build_game_opportunities
from scripts.pipeline_validation import require, sha256_file, verify_hash
from scripts.rebuild_grouped_events import migrate_unaffected, SOURCES
from scripts.recorded_attempt_baseline import ROOT


def check_game(task):
    source, cached = task
    row = pd.Series(source)
    verify_hash(ROOT / row.cache_path, row.sha256)
    verify_hash(ROOT / cached['output_path'], cached['output_sha256'])
    old = pd.read_csv(ROOT / cached['output_path'], low_memory=False)
    observed, metadata = build_game_opportunities(
        row, json.loads((ROOT / row.cache_path).read_bytes()),
        group_linked_outcomes=True, include_movement_evidence=True)
    require(metadata['movement_evidence_actions'] == 0, 'Migration sample contains omitted actions')
    expected = migrate_unaffected(old)
    # Normalize CSV missing-value representation exactly as the production handoff.
    observed = pd.read_csv(StringIO(observed.to_csv(index=False)), low_memory=False)
    pd.testing.assert_frame_equal(expected, observed, check_dtype=False, check_like=True, check_exact=True)
    return dict(game_pk=int(row.game_pk), season=int(row.season), windows=len(observed), columns=len(observed.columns))


def main():
    parent = resolve_run(ROOT / 'results/grouped_event_rebuild', ROOT / 'data/processed/grouped_event_rebuild')
    inventory = resolve_run(ROOT / 'results/movement_evidence_inventory', ROOT / 'data/processed/movement_evidence_inventory')
    omitted = set(pd.read_csv(inventory.local / 'candidates.csv.gz').game_pk)
    metadata = pd.read_csv(parent.results / 'games.csv').set_index('game_pk')
    require(metadata.parser_version.eq('historical_processing_v2_grouped').all(), 'Expected preserved G2 parent')
    manifests = pd.concat([pd.read_csv(ROOT / f'data/historical_feed_manifest_{year}.csv')
                           for year in (2022, 2023, 2024)], ignore_index=True)
    eligible = manifests[manifests.feed_eligible.eq(True) & ~manifests.game_pk.isin(omitted)]
    selected = eligible.groupby('season', group_keys=False).sample(n=20, random_state=20261116)
    tasks = [(row, metadata.loc[row['game_pk']].to_dict()) for row in selected.to_dict('records')]
    with ProcessPoolExecutor(max_workers=4) as pool:
        checks = list(pool.map(check_game, tasks))
    result = dict(parent_manifest_sha256=sha256_file(parent.results / 'manifest.json'),
                  inventory_manifest_sha256=sha256_file(inventory.results / 'manifest.json'),
                  source_hashes={name: sha256_file(ROOT / name) for name in SOURCES},
                  games=len(checks), windows=sum(row['windows'] for row in checks), checks=checks)
    (ROOT / 'results/movement_migration_verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Exact source-reparse equivalence:', result['games'], 'games;', result['windows'], 'windows')


if __name__ == '__main__':
    main()
