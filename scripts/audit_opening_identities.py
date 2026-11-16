"""Audit explicit pitcher-substitution chronology across development feeds."""
import json

import pandas as pd

from scripts.artifact_runs import StagedRun
from scripts.opening_identities import pitcher_timeline
from scripts.pipeline_validation import ValidationError, current_environment, require, sha256_file, verify_hash
from scripts.recorded_attempt_baseline import ROOT


def main():
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    manifests = pd.concat([pd.read_csv(ROOT / f'data/historical_feed_manifest_{year}.csv')
                           for year in (2022, 2023, 2024)], ignore_index=True)
    manifests = manifests[manifests.feed_eligible.eq(True)]
    require(len(manifests) == 7289 and manifests.game_pk.is_unique, 'Manifest coverage mismatch')
    stage = StagedRun(ROOT / 'results/opening_identity_audit', ROOT / 'data/processed/opening_identity_audit')
    rows, errors = [], []
    for index, row in enumerate(manifests.itertuples(index=False), 1):
        path = ROOT / row.cache_path
        verify_hash(path, row.sha256)
        feed = json.loads(path.read_bytes())
        try:
            snapshots, events, changes = pitcher_timeline(feed)
            rows.append(dict(game_pk=row.game_pk, season=row.season, sha256=row.sha256,
                             pitcher_changes=sum(change[2] for change in changes),
                             batter_changes=sum(change[3] for change in changes),
                             events=len(events)))
        except ValidationError as error:
            errors.append(dict(game_pk=row.game_pk, season=row.season, sha256=row.sha256, reason=str(error)))
        if index % 500 == 0:
            print(f'Audited pitcher chronology for {index}/7289 games', flush=True)
    pd.DataFrame(rows).to_csv(stage.paths.results / 'games.csv', index=False)
    pd.DataFrame(errors, columns=['game_pk', 'season', 'sha256', 'reason']).to_csv(stage.paths.results / 'exceptions.csv', index=False)
    manifests[['game_pk', 'season', 'cache_path', 'sha256']].to_csv(stage.paths.local / 'sources.csv', index=False)
    provenance = dict(environment=current_environment(), verified_games=len(rows), unresolved_games=len(errors),
                      source_hashes={name: sha256_file(ROOT / name) for name in
                                     ['scripts/opening_identities.py', 'scripts/audit_opening_identities.py']})
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        require(len(pd.read_csv(paths.results / 'games.csv')) + len(pd.read_csv(paths.results / 'exceptions.csv')) == 7289,
                'Incomplete identity audit')

    paths = stage.publish(validate)
    print(json.dumps(provenance, indent=2))
    print(pd.DataFrame(errors).to_string(index=False))
    print(paths.results)


if __name__ == '__main__':
    main()
