"""Frozen recorded pitcher-pickoff response analysis; no 2025 access."""
import json
import warnings
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.exceptions import ConvergenceWarning
from scripts.recorded_attempt_baseline import ROOT, NUM, CAT, BINS, metrics, calibration
from scripts.artifact_runs import StagedRun, resolve_run
from scripts.pipeline_validation import require, verify_hash, sha256_file, current_environment

TARGET='recorded_pitcher_pickoff_indicator'
CATEGORIES=CAT+['pitcher_id','opening_catcher_id']

def features(frame, threat=None, depth=False):
    x=frame[NUM+CATEGORIES].copy()
    for column in CATEGORIES:
        x[column]=x[column].fillna('MISSING').astype(str)
    if threat:
        p=frame[threat].clip(1e-8,1-1e-8)
        require(p.notna().all(),'Missing prospective threat')
        x['threat_logit']=np.log(p/(1-p))
    if depth:
        for era in ['pre_2023','post_2023']:
            n=frame[f'runner_prior_{era}_eligible_opportunities']
            x[era+'_log_exposure']=np.log1p(n)
            x[era+'_cold']=n.eq(0).astype(int)
    return x

def fit(train, threat=None, depth=False):
    x=features(train,threat,depth)
    numeric=[c for c in x if c not in CATEGORIES]
    preprocessing=ColumnTransformer([
        ('numeric',make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler()),numeric),
        ('categorical',OneHotEncoder(handle_unknown='ignore'),CATEGORIES)])
    model=make_pipeline(preprocessing,LogisticRegression(C=1,solver='lbfgs',max_iter=2000))
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        model.fit(x,train[TARGET].astype(int))
    return model

def validate(paths):
    m=pd.read_csv(paths.results/'metrics.csv')
    expected={(split,variant,model)
              for split in ['diagnostic_2023','development_2024']
              for variant in ['primary','calibrated_threat','history_depth','known_initiator']
              for model in ['constant','context','context_threat']}
    require(len(m)==len(expected) and set(zip(m.split,m.variant,m.model))==expected,
            'Incomplete or duplicated model results')
    require(np.isfinite(m[['log_loss','brier','average_precision']]).all().all(),'Invalid metrics')
    for (split,variant),g in m.groupby(['split','variant']):
        require(g.n.nunique()==1 and g.attempts.nunique()==1,'Unmatched comparison populations')
    for filename,keys in [('calibration.csv',['split','variant','model']),('subgroups.csv',['split','variant','model','subgroup'])]:
        table=pd.read_csv(paths.results/filename)
        require(set(zip(table.split,table.variant,table.model))==set(zip(m.split,m.variant,m.model)), 'Incomplete calibration/subgroup coverage')
        for key,g in table.groupby(keys):
            row=m[(m.split==key[0])&(m.variant==key[1])&(m.model==key[2])].iloc[0]
            require(g.n.sum()==row.n and g.events.sum()==row.attempts,'Calibration/subgroup accounting mismatch')
    for name in ['bootstrap.csv','calibration.csv','subgroups.csv','sample_flow.csv','provenance.json']:
        require((paths.results/name).is_file(),f'Missing {name}')
    bootstrap=pd.read_csv(paths.results/'bootstrap.csv')
    bootstrap_keys={(split,variant,cluster,metric)
                    for split,variant,_model in expected
                    for cluster in ['game_pk','pitcher_id','runner_id']
                    for metric in ['log_loss','brier','average_precision']}
    require(len(bootstrap)==len(bootstrap_keys)
            and set(zip(bootstrap.split,bootstrap.variant,bootstrap.cluster,bootstrap.metric))==bootstrap_keys,
            'Incomplete bootstrap comparisons')
    require(np.isfinite(bootstrap[['delta','lower','upper']]).all().all()
            and bootstrap.lower.le(bootstrap.upper).all(),'Invalid bootstrap intervals')

def main(*, input_dir=None, verified_hashes=None, forward_results=None, forward_local=None,
         output_dir=None, local_dir=None, definition_provenance=None):
    require(not (ROOT/'data/historical_feed_manifest_2025.csv').exists(),'2025 remains closed')
    source=resolve_run(forward_results or ROOT/'results/forward_threat_v2',
                       forward_local or ROOT/'data/processed/forward_threat_v2')
    inputs=Path(input_dir) if input_dir is not None else ROOT/'data/processed/chronology_repair'
    if verified_hashes is None:
        expected=json.loads((ROOT/'results/chronology_repair/repaired_provenance.json').read_text())['repaired_input_hashes']
    else:
        expected=dict(verified_hashes)
    forward_provenance=json.loads((source.results/'provenance.json').read_text(encoding='utf-8'))
    for year in (2023,2024):
        require(forward_provenance['hashes'][str(year)] == expected[str(year)],
                f'Threat scores use a different opportunity snapshot: {year}')
    frames={}; hashes={}
    for year in (2023,2024):
        path=inputs/f'opportunities_{year}.csv.gz'
        hashes[str(year)]=verify_hash(path,expected[str(year)])
        frame=pd.read_csv(path,low_memory=False)
        score_path=source.local/('training_forward_scores.csv.gz' if year==2023 else 'development_2024_scores.csv.gz')
        scores=pd.read_csv(score_path)
        if year==2023: scores=scores[scores.season.eq(2023)]
        hashes[f'scores_{year}']=sha256_file(score_path)
        frame=frame.merge(scores[['opportunity_id','raw','prospective_calibrated']],on='opportunity_id',validate='one_to_one',how='left')
        require(frame.raw.notna().all(),'Unavailable threat score')
        require(frame[TARGET].eq(frame.recorded_pitcher_pickoff_count.gt(0)).all(),'Response-label mismatch')
        frames[year]=frame
    train,test=frames[2023],frames[2024]
    end=pd.to_datetime(train.history_available_after_utc,utc=True,format='mixed')
    start=pd.to_datetime(train.feed_game_start_utc,utc=True,format='mixed')
    require(end.lt(pd.Timestamp('2024-01-01',tz='UTC')).all(),'Unavailable final training games')
    split=pd.Timestamp('2023-07-01',tz='UTC')
    partitions=[('diagnostic_2023',train[end.lt(split)],train[start.ge(split)]),('development_2024',train,test)]
    stage=StagedRun(output_dir or ROOT/'results/pitcher_response',
                    local_dir or ROOT/'data/processed/pitcher_response')
    out,local=stage.paths.results,stage.paths.local
    rows=[]; bins=[]; subgroups=[]; uncertainty=[]; flow=[]
    variants=[('primary','raw',False,False),('calibrated_threat','prospective_calibrated',False,False),('history_depth','raw',True,False),('known_initiator','raw',False,True)]
    for split_name,fitting,scoring in partitions:
        for variant,threat,depth,known in variants:
            a=fitting[~fitting.recorded_unknown_pickoff_indicator] if known else fitting
            b=scoring[~scoring.recorded_unknown_pickoff_indicator] if known else scoring
            require(not set(a.game_pk)&set(b.game_pk),'Fit/score game overlap')
            y=b[TARGET].astype(int).to_numpy()
            flow.append(dict(split=split_name,variant=variant,fit_n=len(a),fit_games=a.game_pk.nunique(),fit_events=int(a[TARGET].sum()),n=len(b),games=b.game_pk.nunique(),events=int(y.sum()),terminal=int(b.terminal_window.sum()),runner_change=int(b.runner_identity_changed_within_window.sum()),unknown=int(b.recorded_unknown_pickoff_indicator.sum()),catcher=int(b.recorded_catcher_pickoff_indicator.sum())))
            predictions=b[['opportunity_id','game_pk',TARGET]].copy(); ps={}
            for name,feature in [('constant',None),('context',None),('context_threat',threat)]:
                if name=='constant': p=np.full(len(b),a[TARGET].mean())
                else:
                    model=fit(a,feature,depth); p=model.predict_proba(features(b,feature,depth))[:,1]
                    path=local/f'{split_name}_{variant}_{name}.joblib'
                    joblib.dump(dict(model=model,threat=feature,depth=depth),path)
                    restored=joblib.load(path)
                    np.testing.assert_allclose(p,restored['model'].predict_proba(features(b,feature,depth))[:,1],rtol=0,atol=0)
                ps[name]=p; predictions[name]=p
                intercept,slope=calibration(y,p)
                rows.append(dict(split=split_name,variant=variant,model=name,n=len(b),attempts=int(y.sum()),mean_prediction=p.mean(),observed_rate=y.mean(),calibration_intercept=intercept,calibration_slope=slope,**metrics(y,p)))
                table=pd.DataFrame(dict(y=y,p=p,bin=pd.cut(p,BINS,include_lowest=True)))
                for label,g in table.groupby('bin',observed=False): bins.append(dict(split=split_name,variant=variant,model=name,bin=str(label),n=len(g),events=int(g.y.sum()),mean_prediction=g.p.mean(),observed_rate=g.y.mean()))
                axes={'disengagements':b.recorded_disengagements_at_open.astype(str),'history_depth':pd.cut(b.runner_prior_all_regimes_eligible_opportunities,[-1,0,50,200,np.inf]).astype(str),'terminal':b.terminal_window.astype(str),'runner_change':b.runner_identity_changed_within_window.astype(str),'unseen_pitcher':(~b.pitcher_id.isin(a.pitcher_id)).astype(str),'unseen_catcher':(~b.opening_catcher_id.isin(a.opening_catcher_id)).astype(str)}
                for axis,values in axes.items():
                    for value in sorted(values.unique()):
                        mask=values.eq(value).to_numpy()
                        subgroups.append(dict(split=split_name,variant=variant,model=name,subgroup=axis,value=value,n=int(mask.sum()),events=int(y[mask].sum()),mean_prediction=p[mask].mean(),observed_rate=y[mask].mean()))
            predictions.to_csv(local/f'{split_name}_{variant}_predictions.csv.gz',index=False)
            for cluster in ['game_pk','pitcher_id','runner_id']:
                codes,groups=pd.factorize(b[cluster]); require((codes>=0).all(),'Missing cluster identity')
                rng=np.random.default_rng(20261115); draws=[]
                for _ in range(500):
                    w=rng.multinomial(len(groups),np.full(len(groups),1/len(groups)))[codes]
                    baseline=metrics(y,ps['context'],w); augmented=metrics(y,ps['context_threat'],w)
                    draws.append([augmented[k]-baseline[k] for k in baseline])
                for j,metric in enumerate(baseline):
                    lo,hi=np.quantile(np.array(draws)[:,j],[.025,.975])
                    uncertainty.append(dict(split=split_name,variant=variant,cluster=cluster,metric=metric,delta=metrics(y,ps['context_threat'])[metric]-metrics(y,ps['context'])[metric],lower=lo,upper=hi))
            print(split_name,variant,'completed',flush=True)
    for name,data in [('metrics',rows),('calibration',bins),('subgroups',subgroups),('bootstrap',uncertainty),('sample_flow',flow)]: pd.DataFrame(data).to_csv(out/f'{name}.csv',index=False)
    hashes['protocol']=sha256_file(ROOT/'docs/pitcher_response_protocol.md'); hashes['script']=sha256_file(__file__)
    (out/'provenance.json').write_text(json.dumps(dict(hashes=hashes,environment=current_environment(),
        definition_provenance=dict(definition_provenance or {})),indent=2)+'\n')
    completed=stage.publish(validate)
    print('Published:',completed)
    return completed

if __name__=='__main__': main()
