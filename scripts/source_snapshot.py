"""Check that repaired histories use the feed snapshot actually audited."""
import pandas as pd
from scripts.pipeline_validation import require


def validate_source_snapshot(opportunities, audit, dispositions, manifests):
    """Reject missing, duplicate, stale, or inconsistent per-game provenance."""
    tables = {'audit': audit, 'dispositions': dispositions, 'manifests': manifests}
    for name, table in tables.items():
        require(table.game_pk.notna().all() and table.game_pk.is_unique,
                f'{name}: game IDs must be present and unique')
        column = 'sha256' if name == 'manifests' else 'source_sha256'
        require(table[column].notna().all()
                and table[column].astype(str).str.fullmatch('[0-9a-f]{64}').all(),
                f'{name}: invalid source hashes')
    expected = audit.set_index('game_pk')
    game_ids = set(expected.index)
    for name, table in tables.items():
        require(set(table.game_pk) == game_ids, f'{name}: game coverage differs from audit')
        column = 'sha256' if name == 'manifests' else 'source_sha256'
        require(table[column].eq(table.game_pk.map(expected.source_sha256)).all(),
                f'{name}: source hashes differ from audited feeds')
    require(opportunities.opportunity_id.notna().all() and opportunities.opportunity_id.is_unique,
            'Opportunity IDs must be present and unique')
    require(set(opportunities.game_pk) == game_ids, 'Opportunity game coverage differs from audit')
    matches = opportunities.source_sha256.eq(opportunities.game_pk.map(expected.source_sha256))
    mismatched = opportunities.loc[~matches, 'game_pk'].unique().tolist()
    require(matches.all(), f'Opportunity source snapshot differs from audit for games {mismatched[:10]}')
    require(opportunities.season.eq(opportunities.game_pk.map(expected.season)).all(),
            'Opportunity seasons differ from audit')
    for column in ['freeze_time', 'last_observed_time']:
        observed = pd.to_datetime(dispositions[column], utc=True, format='mixed')
        audited = pd.to_datetime(dispositions.game_pk.map(expected[column]), utc=True, format='mixed')
        require(observed.notna().all() and observed.eq(audited).all(),
                f'Disposition {column} differs from audited bounds')
    available = pd.to_datetime(dispositions.available_after, utc=True, format='mixed')
    last = pd.to_datetime(dispositions.last_observed_time, utc=True, format='mixed')
    require(available.notna().all() and available.ge(last).all(),
            'History availability precedes the last audited event')
