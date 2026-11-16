"""Reload corrected model bundles and independently recompute saved metrics."""
import argparse
import json

import joblib
import numpy as np
import pandas as pd

from scripts.artifact_runs import resolve_run
from scripts.forward_threat import apply_calibration
from scripts.pipeline_validation import require, sha256_file
from scripts.recorded_attempt_baseline import LABEL, MODELS, ROOT, metrics, predict


def main(stage):
    histories = resolve_run(ROOT / 'results/grouped_histories', ROOT / 'data/processed/grouped_histories')
    data = pd.concat([pd.read_csv(histories.local / f'opportunities_{year}.csv.gz', low_memory=False)
                      for year in (2022, 2023, 2024)], ignore_index=True).set_index('opportunity_id')
    labels = {'baseline': 'recorded_attempt_grouped', 'forward': 'forward_threat_grouped',
              'response': 'pitcher_response_grouped'}
    label = labels[stage]
    run = resolve_run(ROOT / 'results' / label, ROOT / 'data/processed' / label)
    table = pd.read_csv(run.results / 'metrics.csv')
    reloaded = comparisons = 0

    def compare_metrics(saved, probabilities, target):
        nonlocal comparisons
        for name, value in metrics(target, probabilities).items():
            np.testing.assert_allclose(value, saved[name], rtol=1e-10, atol=1e-12)
            comparisons += 1

    if stage == 'forward':
        scores = pd.read_csv(run.local / 'training_forward_scores.csv.gz', float_precision='round_trip')
        require(set(scores.opportunity_id) == set(data[data.season.le(2023)].index), 'Training score coverage')
        for origin, group in scores[scores.raw.notna()].groupby('origin'):
            bundle = joblib.load(run.local / f'model_{pd.Timestamp(origin):%Y_%m}.joblib')
            frame = data.loc[group.opportunity_id]
            p = predict(bundle['base'], frame)
            q = apply_calibration(bundle['calibrator'], p)
            np.testing.assert_allclose(p, group.raw, rtol=1e-12, atol=1e-14)
            np.testing.assert_allclose(q, group.prospective_calibrated, rtol=1e-12, atol=1e-14)
            reloaded += len(group)
        development = pd.read_csv(run.local / 'development_2024_scores.csv.gz', float_precision='round_trip')
        require(set(development.opportunity_id) == set(data[data.season.eq(2024)].index), 'Development coverage')
        bundle = joblib.load(run.local / 'final_bundle.joblib')
        p = predict(bundle['base'], data.loc[development.opportunity_id])
        q = apply_calibration(bundle['candidate_calibrator'], p)
        np.testing.assert_allclose(p, development.raw, rtol=1e-12, atol=1e-14)
        np.testing.assert_allclose(q, development.prospective_calibrated, rtol=1e-12, atol=1e-14)
        selected = q if bundle['selected_policy'] == 'logistic_recalibration' else p
        np.testing.assert_allclose(selected, development.selected_probability, rtol=1e-12, atol=1e-14)
        reloaded += len(development)
        selection = pd.to_datetime(scores.start, utc=True, format='ISO8601').ge(pd.Timestamp('2023-07-01', tz='UTC'))
        groups = {'forward_2022': scores[scores.season.eq(2022) & scores.raw.notna()],
                  'forward_2023': scores[scores.season.eq(2023) & scores.raw.notna()],
                  'selection_2023': scores[selection & scores.raw.notna()],
                  'development_2024': development}
        for row in table.to_dict('records'):
            group = groups[row['split']]
            compare_metrics(row, group[row['model']], group[LABEL])
    else:
        if stage == 'response':
            from scripts.pitcher_response import TARGET, features
            forward = resolve_run(ROOT / 'results/forward_threat_grouped', ROOT / 'data/processed/forward_threat_grouped')
            scores = pd.concat([pd.read_csv(forward.local / name) for name in
                                ('training_forward_scores.csv.gz', 'development_2024_scores.csv.gz')])
            data = data.join(scores.set_index('opportunity_id')[['raw', 'prospective_calibrated']], validate='one_to_one')
        else:
            TARGET = LABEL
        for row in table.to_dict('records'):
            stem = row['split'] + ('_' + row['variant'] if stage == 'response' else '')
            saved = pd.read_csv(run.local / f'{stem}_predictions.csv.gz', float_precision='round_trip')
            frame = data.loc[saved.opportunity_id]
            require(np.array_equal(saved[TARGET].to_numpy(), frame[TARGET].to_numpy()), 'Saved target mismatch')
            compare_metrics(row, saved[row['model']], saved[TARGET])
            if stage == 'baseline' and row['split'] == 'heldout_2024':
                bundle = joblib.load(run.local / f'{row["model"]}.joblib')
                p = predict(bundle, frame)
            elif stage == 'response' and row['model'] != 'constant':
                bundle = joblib.load(run.local / f'{stem}_{row["model"]}.joblib')
                p = bundle['model'].predict_proba(features(frame, bundle['threat'], bundle['depth']))[:, 1]
            else:
                continue
            np.testing.assert_allclose(p, saved[row['model']], rtol=1e-12, atol=1e-14)
            reloaded += len(frame)
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), '2025 remains closed')
    result = dict(stage=stage, run_id=run.results.name,
                  manifest_sha256=sha256_file(run.results / 'manifest.json'),
                  history_manifest_sha256=sha256_file(histories.results / 'manifest.json'),
                  verifier_sha256=sha256_file(__file__), reloaded_predictions=reloaded,
                  independently_recomputed_metrics=comparisons, test_season_opened=False)
    output = ROOT / 'results/grouped_model_verification'
    output.mkdir(exist_ok=True)
    (output / f'{stage}_{run.results.name}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['baseline', 'forward', 'response'])
    main(parser.parse_args().stage)
