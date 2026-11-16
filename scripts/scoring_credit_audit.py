"""Reconcile explicit all-base-state event tags with player/game box scores."""
from collections import Counter
import json

import pandas as pd

from scripts.artifact_runs import StagedRun
from scripts.pipeline_validation import current_environment, require, sha256_file, verify_hash
from scripts.recorded_attempt_baseline import ROOT

SB_TAGS = {f'stolen_base_{base}' for base in ('2b', '3b', 'home')}
CS_TAGS = {f'{prefix}_{base}' for prefix in ('caught_stealing', 'pickoff_caught_stealing')
           for base in ('2b', '3b', 'home')}


def reconcile(feed):
    candidates, official, vocabulary, issues = Counter(), {}, Counter(), []
    movement_candidates = Counter()
    boxscore_sides = Counter()
    for play in feed['liveData']['plays']['allPlays']:
        seen_movements = set()
        for movement in play.get('runners', []):
            detail = movement.get('details', {})
            tag = detail.get('eventType', '') or ''
            reason = detail.get('movementReason', '') or ''
            if 'stolen_base' not in tag + reason and 'caught_stealing' not in tag + reason:
                continue
            vocabulary[f'movement:{tag}:{reason}'] += 1
            category = 'sb' if reason in {'r_' + value for value in SB_TAGS} else (
                'cs' if reason in {'r_' + value for value in CS_TAGS} else None)
            if category is None:
                continue
            actor = detail.get('runner', {}).get('id')
            if actor is None:
                issues.append(dict(at_bat_index=play['about']['atBatIndex'],
                                   event_index=detail.get('playIndex'), event_type=tag, issue='missing_movement_actor'))
                continue
            key = (detail.get('playIndex'), int(actor), reason)
            if key not in seen_movements:
                movement_candidates[(int(actor), category)] += 1
                seen_movements.add(key)
        for event in play.get('playEvents', []):
            tag = event.get('details', {}).get('eventType', '') or ''
            if 'stolen_base' not in tag and 'caught_stealing' not in tag:
                continue
            vocabulary[tag] += 1
            category = 'sb' if tag in SB_TAGS else 'cs' if tag in CS_TAGS else None
            if category is None:
                continue
            actor = event.get('player', {}).get('id')
            if actor is None:
                issues.append(dict(at_bat_index=play['about']['atBatIndex'],
                                   event_index=event['index'], event_type=tag, issue='missing_actor'))
                continue
            candidates[(int(actor), category)] += 1
    for side in ('home', 'away'):
        for person in feed['liveData']['boxscore']['teams'][side]['players'].values():
            batting = person.get('stats', {}).get('batting', {})
            if not batting:
                continue
            player = int(person['person']['id'])
            require('stolenBases' in batting and 'caughtStealing' in batting, 'Missing box-score credit fields')
            # A traded player can appear for both sides of a resumed game.
            previous_sb, previous_cs = official.get(player, (0, 0))
            official[player] = (previous_sb + int(batting['stolenBases']),
                                previous_cs + int(batting['caughtStealing']))
            boxscore_sides[player] += 1
    players = set(official) | {player for player, category in candidates} | {
        player for player, category in movement_candidates}
    rows = []
    for player in sorted(players):
        sb, cs = official.get(player, (None, None))
        tagged_sb, tagged_cs = candidates[(player, 'sb')], candidates[(player, 'cs')]
        movement_sb, movement_cs = movement_candidates[(player, 'sb')], movement_candidates[(player, 'cs')]
        rows.append(dict(player_id=player, boxscore_present=player in official,
                         boxscore_sides=boxscore_sides[player],
                         tagged_sb=tagged_sb, boxscore_sb=sb, tagged_cs=tagged_cs, boxscore_cs=cs,
                         movement_sb=movement_sb, movement_cs=movement_cs,
                         movement_agrees=player in official and movement_sb == sb and movement_cs == cs,
                         agrees=player in official and tagged_sb == sb and tagged_cs == cs))
    return rows, vocabulary, issues


def main():
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    manifests = pd.concat([pd.read_csv(ROOT / f'data/historical_feed_manifest_{year}.csv')
                           for year in (2022, 2023, 2024)], ignore_index=True)
    manifests = manifests[manifests.feed_eligible.eq(True)]
    require(len(manifests) == 7289 and manifests.game_pk.is_unique, 'Incomplete development coverage')
    stage = StagedRun(ROOT / 'results/scoring_credit_audit', ROOT / 'data/processed/scoring_credit_audit')
    records, issues, vocabulary = [], [], Counter()
    for index, row in enumerate(manifests.itertuples(index=False), 1):
        path = ROOT / row.cache_path
        verify_hash(path, row.sha256)
        results, tags, exceptions = reconcile(json.loads(path.read_bytes()))
        records.extend(dict(game_pk=row.game_pk, season=row.season, **record) for record in results)
        issues.extend(dict(game_pk=row.game_pk, season=row.season, **record) for record in exceptions)
        vocabulary.update({(row.season, tag): count for tag, count in tags.items()})
        if index % 1000 == 0:
            print(f'Reconciled {index}/7289 game box scores', flush=True)
    table = pd.DataFrame(records)
    table.to_csv(stage.paths.local / 'player_game_reconciliation.csv.gz', index=False)
    table[~table.agrees].to_csv(stage.paths.results / 'disagreements.csv', index=False)
    table[~table.movement_agrees].to_csv(stage.paths.results / 'movement_disagreements.csv', index=False)
    pd.DataFrame(issues, columns=['game_pk', 'season', 'at_bat_index', 'event_index', 'event_type', 'issue']).to_csv(
        stage.paths.results / 'exceptions.csv', index=False)
    pd.DataFrame([dict(season=season, event_type=tag, count=count) for (season, tag), count in vocabulary.items()]).to_csv(
        stage.paths.results / 'event_vocabulary.csv', index=False)
    summary = table.groupby('season').agg(games=('game_pk', 'nunique'), player_games=('player_id', 'size'),
                                        agreeing=('agrees', 'sum'), tagged_sb=('tagged_sb', 'sum'),
                                        boxscore_sb=('boxscore_sb', 'sum'), tagged_cs=('tagged_cs', 'sum'),
                                        boxscore_cs=('boxscore_cs', 'sum'))
    summary['movement_sb'] = table.groupby('season').movement_sb.sum()
    summary['movement_cs'] = table.groupby('season').movement_cs.sum()
    summary['movement_disagreements'] = table.groupby('season').movement_agrees.apply(lambda values: (~values).sum())
    summary['disagreements'] = summary.player_games - summary.agreeing
    summary.to_csv(stage.paths.results / 'summary.csv')
    manifests[['game_pk', 'season', 'sha256']].to_csv(stage.paths.results / 'source_hashes.csv', index=False)
    provenance = dict(environment=current_environment(), source_sha256=sha256_file(__file__),
                      protocol_sha256=sha256_file(ROOT / 'docs/scoring_credit_audit_protocol.md'),
                      sb_tags=sorted(SB_TAGS), cs_tags=sorted(CS_TAGS), independent_source_validation=False)
    (stage.paths.results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

    def validate(paths):
        saved = pd.read_csv(paths.local / 'player_game_reconciliation.csv.gz')
        require(not saved[['game_pk', 'player_id']].duplicated().any(), 'Duplicate player/game reconciliation')
        require(set(saved.game_pk) == set(manifests.game_pk), 'Incomplete game reconciliation')
        require(len(saved) == summary.player_games.sum(), 'Reconciliation flow mismatch')

    completed = stage.publish(validate)
    print(summary.to_string())
    print('Missing-actor exceptions:', len(issues))
    print(completed.results)


if __name__ == '__main__':
    main()
