"""Accounting checks for a staged recorded-attempt baseline run."""
import numpy as np
import pandas as pd

from scripts.pipeline_validation import require
from scripts.recorded_attempt_baseline import LABEL, MODELS


def validate_baseline_run(paths):
    metrics = pd.read_csv(paths.results / 'metrics.csv')
    expected = {(split, model) for split in ('chronological_training_diagnostic', 'heldout_2024')
                for model in MODELS}
    require(len(metrics) == len(expected) and set(zip(metrics.split, metrics.model)) == expected,
            'Incomplete baseline comparisons')
    require(np.isfinite(metrics[['log_loss', 'brier', 'average_precision']]).all().all(),
            'Nonfinite baseline metrics')
    for split in metrics.split.unique():
        predictions = pd.read_csv(paths.local / f'{split}_predictions.csv.gz')
        require(predictions.opportunity_id.is_unique, 'Duplicate baseline scores')
        require(predictions[MODELS].ge(0).all().all() and predictions[MODELS].le(1).all().all(),
                'Invalid baseline predictions')
        rows = metrics[metrics.split.eq(split)]
        require(rows.n.eq(len(predictions)).all() and rows.attempts.eq(predictions[LABEL].sum()).all(),
                'Baseline score accounting mismatch')
    for filename, keys in [('calibration.csv', ['split', 'model']),
                           ('subgroups.csv', ['split', 'model', 'subgroup'])]:
        table = pd.read_csv(paths.results / filename)
        require(set(zip(table.split, table.model)) == expected, 'Incomplete diagnostic groups')
        for key, group in table.groupby(keys):
            row = metrics[(metrics.split == key[0]) & (metrics.model == key[1])].iloc[0]
            require(group.n.sum() == row.n and group.attempts.sum() == row.attempts,
                    'Baseline diagnostic accounting mismatch')
    for filename in ['sample_flow.csv', 'context_missingness.csv', 'game_bootstrap.csv', 'provenance.json']:
        require((paths.results / filename).is_file(), f'Missing baseline artifact: {filename}')
    for model in MODELS:
        require((paths.local / f'{model}.joblib').is_file(), f'Missing baseline bundle: {model}')
