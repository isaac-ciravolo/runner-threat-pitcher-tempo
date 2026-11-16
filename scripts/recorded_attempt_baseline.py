"""Frozen recorded-attempt baseline; run python -m scripts.recorded_attempt_baseline."""
from scripts.pipeline_validation import require
from pathlib import Path
import hashlib
import json
import platform
import warnings
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss, average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.exceptions import ConvergenceWarning

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'recorded_attempt_baseline'
LOCAL = ROOT / 'data' / 'processed' / 'recorded_attempt_baseline'
LABEL = 'recorded_steal_attempt_indicator'
NUM = ['inning', 'open_balls', 'open_strikes', 'open_outs', 'recorded_disengagements_at_open', 'recorded_disengagement_resets_at_open', 'disengagements_remaining_without_penalty']
CAT = ['half_inning', 'open_timing']
MODELS = ['constant', 'context', 'post_history', 'separate_history']
BINS = [0, .005, .01, .02, .05, .1, .2, 1]

def features(d, variant, prevalence):
    x = d[NUM + CAT].copy()
    post = d.season.ge(2023)
    x['post_rule'] = post.astype(int)
    for c in NUM[-2:]:
        x.loc[~post, c] = 0
    for c in CAT:
        x[c] = x[c].fillna('MISSING').astype(str)
    blocks = [] if variant == 'context' else ['post_2023']
    if variant == 'separate_history':
        blocks = ['pre_2023', 'post_2023']
    for block in blocks:
        n = d[f'runner_prior_{block}_eligible_opportunities']
        a = d[f'runner_prior_{block}_attempted_opportunities']
        require(n.notna().all() and a.notna().all() and (a <= n).all(), 'Validation failed: n.notna().all() and a.notna().all() and (a <= n).all()')
        x[block + '_log_exposure'] = np.log1p(n)
        x[block + '_rate'] = (a + 100 * prevalence) / (n + 100)
        x[block + '_cold'] = n.eq(0).astype(int)
    return x

def fit(train, variant):
    p = float(train[LABEL].mean())
    if variant == 'constant':
        return {'prevalence': p, 'variant': variant, 'pipeline': None, 'calibration': 'identity'}
    x = features(train, variant, p)
    numeric = [c for c in x if c not in CAT]
    prep = ColumnTransformer([
        ('numeric', make_pipeline(SimpleImputer(strategy='median', add_indicator=True), StandardScaler()), numeric),
        ('categorical', OneHotEncoder(handle_unknown='ignore'), CAT)])
    model = make_pipeline(prep, LogisticRegression(C=1, solver='lbfgs', max_iter=2000))
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        model.fit(x, train[LABEL].astype(int))
    return {'prevalence': p, 'variant': variant, 'pipeline': model, 'calibration': 'identity'}

def predict(model, d):
    if model['pipeline'] is None:
        return np.full(len(d), model['prevalence'])
    return model['pipeline'].predict_proba(features(d, model['variant'], model['prevalence']))[:, 1]

def metrics(y, p, weight=None):
    return dict(log_loss=log_loss(y, p, sample_weight=weight, labels=[0,1]),
                brier=brier_score_loss(y, p, sample_weight=weight),
                average_precision=average_precision_score(y, p, sample_weight=weight))

def calibration(y, p):
    if np.ptp(p) < 1e-12:
        return np.nan, np.nan
    z = np.log(np.clip(p, 1e-12, 1-1e-12) / (1-np.clip(p, 1e-12, 1-1e-12)))
    m = LogisticRegression(C=1e10, max_iter=2000).fit(z.reshape(-1,1), y)
    return m.intercept_[0], m.coef_[0,0]

def main():
    OUT.mkdir(exist_ok=True); LOCAL.mkdir(exist_ok=True)
    spec = ROOT / 'docs/recorded_attempt_baseline_spec.md'
    provenance = {'spec_sha256': hashlib.sha256(spec.read_bytes()).hexdigest(), 'inputs': {},
                  'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__, 'sklearn': sklearn.__version__}
    require(not (ROOT / 'data/historical_feed_manifest_2025.csv').exists(), "Validation failed: not (ROOT / 'data/historical_feed_manifest_2025.csv').exists()")
    frames = []
    for year in (2022,2023,2024):
        path = ROOT / f'data/processed/historical/development/opportunities_{year}.csv.gz'
        provenance['inputs'][str(year)] = hashlib.sha256(path.read_bytes()).hexdigest()
        d = pd.read_csv(path, low_memory=False)
        require(d.season.eq(year).all() and d.opportunity_id.is_unique, 'Validation failed: d.season.eq(year).all() and d.opportunity_id.is_unique')
        for c in ['history_frozen_before_game', 'runner_history_coverage_complete_since_2022_start', 'game_chronology_available']:
            require(d[c].eq(True).all(), c)
        require(d.known_state_conflict.eq(False).all() and d.unknown_action_classification_count.eq(0).all(), 'Validation failed: d.known_state_conflict.eq(False).all() and d.unknown_action_classification_count.eq(0).all()')
        require(d[LABEL].eq(d.recorded_steal_attempt_record_count.gt(0)).all(), 'Validation failed: d[LABEL].eq(d.recorded_steal_attempt_record_count.gt(0)).all()')
        frames.append(d)
    data = pd.concat(frames, ignore_index=True)
    flow = data.groupby('season').agg(windows=('opportunity_id','size'), games=('game_pk','nunique'), attempts=(LABEL,'sum'), terminal=('terminal_window','sum'), runner_change=('runner_identity_changed_within_window','sum'), history_eligible=('attempt_history_eligible','sum'))
    flow['excluded_model_rows'] = 0; flow['attempt_rate'] = flow.attempts / flow.windows
    flow.to_csv(OUT / 'sample_flow.csv')
    data.groupby('season')[NUM + CAT].agg(lambda v: v.isna().sum()).to_csv(OUT / 'context_missingness.csv')
    train = data[data.season.le(2023)]
    start = pd.to_datetime(train.feed_game_start_utc, utc=True, format='mixed')
    end = pd.to_datetime(train.feed_completion_time_utc, utc=True, format='mixed')
    cutoff = pd.Timestamp('2023-07-01', tz='UTC')
    require(end.lt(pd.Timestamp('2024-01-01', tz='UTC')).all(), "Validation failed: end.lt(pd.Timestamp('2024-01-01', tz='UTC')).all()")
    partitions = [('chronological_training_diagnostic', train[end.lt(cutoff)], train[start.ge(cutoff)]), ('heldout_2024', train, data[data.season.eq(2024)])]
    rows, bins, groups, intervals = [], [], [], []
    for split, fitting, scoring in partitions:
        print(split, len(fitting), len(scoring), flush=True)
        y = scoring[LABEL].astype(int).to_numpy()
        predictions = scoring[['opportunity_id','game_pk','season',LABEL]].copy()
        ps = {}
        for name in MODELS:
            model = fit(fitting, name); p = predict(model, scoring); ps[name] = p
            predictions[name] = p
            intercept, slope = calibration(y,p)
            rows.append(dict(split=split, model=name, fit_n=len(fitting), fit_attempts=int(fitting[LABEL].sum()), n=len(y), attempts=int(y.sum()), prevalence=float(y.mean()), mean_prediction=float(p.mean()), calibration_intercept=intercept, calibration_slope=slope, **metrics(y,p)))
            if split == 'heldout_2024':
                joblib.dump(model, LOCAL / f'{name}.joblib')
            table = pd.DataFrame({'y':y,'p':p,'bin':pd.cut(p,BINS,include_lowest=True)})
            for b,g in table.groupby('bin',observed=False):
                bins.append(dict(split=split,model=name,bin=str(b),n=len(g),attempts=int(g.y.sum()),mean_prediction=g.p.mean(),observed_rate=g.y.mean()))
            subgroup_values = {'disengagements':scoring.recorded_disengagements_at_open.astype(str), 'history_depth':pd.cut(scoring.runner_prior_all_regimes_eligible_opportunities,[-1,0,50,200,np.inf]).astype(str), 'terminal':scoring.terminal_window.astype(str), 'runner_change':scoring.runner_identity_changed_within_window.astype(str)}
            for axis, values in subgroup_values.items():
                for value in sorted(values.unique()):
                    mask = values.eq(value).to_numpy()
                    groups.append(dict(split=split,model=name,subgroup=axis,value=value,n=int(mask.sum()),attempts=int(y[mask].sum()),mean_prediction=float(p[mask].mean()),observed_rate=float(y[mask].mean())))
        predictions.to_csv(LOCAL / f'{split}_predictions.csv.gz',index=False)
        codes, games = pd.factorize(scoring.game_pk)
        rng = np.random.default_rng(20261115)
        draws = {name:[] for name in MODELS}
        for _ in range(200):
            w = rng.multinomial(len(games), np.full(len(games),1/len(games)))[codes]
            for name in MODELS:
                draws[name].append(list(metrics(y,ps[name],w).values()))
        for name in MODELS:
            a = np.array(draws[name]); base = np.array(draws['constant'])
            for j, metric in enumerate(['log_loss','brier','average_precision']):
                low, high = np.quantile(a[:,j],[.025,.975]); dl,dh = np.quantile(a[:,j]-base[:,j],[.025,.975])
                intervals.append(dict(split=split,model=name,metric=metric,lower=low,upper=high,delta_vs_constant_lower=dl,delta_vs_constant_upper=dh))
    for filename, records in [('metrics',rows),('calibration',bins),('subgroups',groups),('game_bootstrap',intervals)]:
        pd.DataFrame(records).to_csv(OUT / f'{filename}.csv',index=False)
    (OUT / 'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(pd.DataFrame(rows).to_string(index=False))

if __name__ == '__main__':
    main()
