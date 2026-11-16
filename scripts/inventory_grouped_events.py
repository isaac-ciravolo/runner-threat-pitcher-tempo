"""Inventory grouping candidates in all cached development feeds, without fitting."""
from collections import Counter
import json

import pandas as pd

from scripts.artifact_runs import StagedRun
from scripts.grouped_events import grouping_plan
from scripts.pipeline_validation import current_environment, require, sha256_file, verify_hash
from scripts.recorded_attempt_baseline import ROOT


def main():
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    stage = StagedRun(ROOT / 'results/grouped_event_inventory',
                      ROOT / 'data/processed/grouped_event_inventory')
    counts, exceptions, crosswalk, sources = Counter(), [], [], []
    manifests = []
    for year in (2022, 2023, 2024):
        frame = pd.read_csv(ROOT / f'data/historical_feed_manifest_{year}.csv')
        manifests.append(frame[frame.feed_eligible.eq(True)])
    manifest = pd.concat(manifests, ignore_index=True)
    require(manifest.game_pk.is_unique and len(manifest) == 7289, 'Development manifest mismatch')
    for number, row in enumerate(manifest.itertuples(index=False), 1):
        path = ROOT / row.cache_path
        verify_hash(path, row.sha256)
        feed = json.loads(path.read_bytes())
        require(feed['gamePk'] == row.game_pk, 'Feed identity mismatch')
        sources.append(dict(game_pk=row.game_pk, season=row.season, sha256=row.sha256))
        for play in feed['liveData']['plays']['allPlays']:
            pa = play['about']['atBatIndex']
            mapping, unresolved = grouping_plan(play)
            lookup = {event['index']: event for event in play.get('playEvents', [])}
            for child, parent in mapping.items():
                event, target = lookup[child], lookup[parent]
                kind = event.get('details', {}).get('eventType', '')
                parent_type = target.get('type', '')
                counts[(row.season, kind, parent_type)] += 1
                crosswalk.append(dict(season=row.season, game_pk=row.game_pk, at_bat_index=pa,
                                      source_event_index=child, effective_event_index=parent,
                                      event_type=kind, parent_type=parent_type,
                                      parent_runner_going=target.get('details', {}).get('runnerGoing')))
            exceptions.extend(dict(season=row.season, game_pk=row.game_pk, at_bat_index=pa, **issue)
                              for issue in unresolved)
        if number % 500 == 0:
            print(f'Inventoried {number}/{len(manifest)} feeds', flush=True)
    summary = pd.DataFrame([dict(season=key[0], event_type=key[1], parent_type=key[2], records=value)
                            for key, value in sorted(counts.items())])
    summary.to_csv(stage.paths.results / 'summary.csv', index=False)
    pd.DataFrame(exceptions, columns=['season', 'game_pk', 'at_bat_index', 'event_index', 'event_type', 'reason']).to_csv(
        stage.paths.results / 'exceptions.csv', index=False)
    pd.DataFrame(crosswalk).to_csv(stage.paths.local / 'crosswalk.csv.gz', index=False)
    pd.DataFrame(sources).to_csv(stage.paths.results / 'sources.csv', index=False)
    provenance = dict(environment=current_environment(),
                      spec_sha256=sha256_file(ROOT / 'docs/grouped_event_repair_protocol.md'),
                      source_hashes={name: sha256_file(ROOT / name) for name in
                                     ['scripts/inventory_grouped_events.py', 'scripts/grouped_events.py']},
                      games=len(sources), mapped_records=len(crosswalk), exceptions=len(exceptions))
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        saved = pd.read_csv(paths.local / 'crosswalk.csv.gz')
        require(not saved.duplicated(['game_pk', 'at_bat_index', 'source_event_index']).any(), 'Duplicate grouping')
        require(len(saved) == pd.read_csv(paths.results / 'summary.csv').records.sum(), 'Grouping accounting')
        require(len(pd.read_csv(paths.results / 'sources.csv')) == 7289, 'Missing sources')

    paths = stage.publish(validate)
    print(json.dumps(provenance, indent=2))
    print(paths.results)


if __name__ == '__main__':
    main()
