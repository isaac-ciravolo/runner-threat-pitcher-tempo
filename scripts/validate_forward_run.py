"""Validation required before a forward run becomes visible to readers."""
import json
import joblib
import numpy as np
import pandas as pd
from scripts.pipeline_validation import require

LABEL = 'recorded_steal_attempt_indicator'


def validate_forward_run(paths):
    metrics = pd.read_csv(paths.results / 'metrics.csv')
    require(metrics[['split', 'model']].duplicated().sum() == 0, 'Duplicate metric rows')
    require(set(metrics.split) == {'forward_2022', 'forward_2023', 'selection_2023', 'development_2024'},
            'Missing evaluation partition')
    require(set(metrics.model) == {'raw', 'prospective_calibrated'}, 'Missing candidate metrics')
    require(len(metrics) == 8, 'Incomplete metric table')
    require(np.isfinite(metrics[['log_loss', 'brier', 'average_precision']]).all().all(),
            'Nonfinite evaluation metrics')
    for filename, keys in [('calibration.csv', ['split', 'model']),
                           ('subgroups.csv', ['split', 'model', 'subgroup'])]:
        table = pd.read_csv(paths.results / filename)
        require(set(zip(table.split, table.model)) == set(zip(metrics.split, metrics.model)),
                f'{filename}: missing model/partition')
        for key, group in table.groupby(keys):
            row = metrics[(metrics.split == key[0]) & (metrics.model == key[1])].iloc[0]
            require(group.n.sum() == row.n and group.attempts.sum() == row.attempts,
                    f'{filename}: denominator mismatch for {key}')
    scores = pd.read_csv(paths.local / 'training_forward_scores.csv.gz')
    require(scores.opportunity_id.is_unique, 'Duplicate training score IDs')
    scored = scores.raw.notna()
    require(scores.loc[scored, 'prospective_calibrated'].notna().all(), 'Missing calibrated scores')
    for column in ['raw', 'prospective_calibrated']:
        require(scores.loc[scored, column].between(0, 1).all(), f'Invalid {column} probabilities')
    flow = pd.read_csv(paths.results / 'sample_flow.csv')
    require(flow.n.sum() == len(scores) and flow.attempts.sum() == scores[LABEL].sum(),
            'Training sample flow does not reconcile')
    origins = pd.read_csv(paths.results / 'origins.csv')
    require(origins.origin.is_unique and set(origins.origin) == set(scores.loc[scored, 'origin']),
            'Origin manifest does not match training scores')
    for row in origins.itertuples():
        date = pd.Timestamp(row.origin)
        group = scores[scores.origin.eq(row.origin)]
        require(len(group) == row.score_n and group[LABEL].sum() == row.score_attempts,
                'Origin accounting mismatch')
        bundle = joblib.load(paths.local / f'model_{date:%Y_%m}.joblib')
        require(bundle['provenance']['origin'] == row.origin, 'Model origin mismatch')
        require(pd.Timestamp(row.fit_max_completion) < date <= pd.Timestamp(row.score_min_start),
                'Base fit is not strictly before scoring')
        if pd.notna(row.calibration_max_completion):
            require(pd.Timestamp(row.calibration_max_completion) < date, 'Calibration is not forward-only')
    development = pd.read_csv(paths.local / 'development_2024_scores.csv.gz')
    require(development.opportunity_id.is_unique, 'Duplicate development score IDs')
    for column in ['raw', 'prospective_calibrated', 'selected_probability']:
        require(development[column].between(0, 1).all(), f'Invalid development {column}')
    expected = metrics[(metrics.split == 'development_2024') & (metrics.model == 'raw')].iloc[0]
    require(len(development) == expected.n and development[LABEL].sum() == expected.attempts,
            'Development accounting mismatch')
    decision = json.loads((paths.results / 'policy.json').read_text(encoding='utf-8'))
    final = joblib.load(paths.local / 'final_bundle.joblib')
    require(final['selected_policy'] == decision['selected_policy'], 'Final policy mismatch')
    require(final['selected_policy'] in {'identity', 'logistic_recalibration'}, 'Unknown policy')
    selected = 'raw' if final['selected_policy'] == 'identity' else 'prospective_calibrated'
    require(development.selected_probability.eq(development[selected]).all(), 'Incorrect selected probabilities')
    # Require all remaining deliverables before the completion pointer can move.
    for name in ['paired_bootstrap.csv', 'chronology_quarantine.csv', 'provenance.json']:
        require((paths.results / name).is_file(), f'Missing artifact: {name}')
    provenance = json.loads((paths.results / 'provenance.json').read_text(encoding='utf-8'))
    require(set(provenance['environment']) == {'python', 'pandas', 'numpy', 'sklearn'}, 'Missing environment metadata')
