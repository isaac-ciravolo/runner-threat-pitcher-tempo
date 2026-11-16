"""Monthly forward threat construction and training-only calibration selection."""
from pathlib import Path
import hashlib, json, warnings
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import ConvergenceWarning
from scripts.recorded_attempt_baseline import ROOT, LABEL, BINS, fit, predict, metrics, calibration
OUT=ROOT/'results/forward_threat'
LOCAL=ROOT/'data/processed/forward_threat'

def logit(p):
    p=np.clip(np.asarray(p),1e-8,1-1e-8)
    return np.log(p/(1-p)).reshape(-1,1)

def fit_calibration(p,y):
    y=np.asarray(y,dtype=int)
    if y.sum()<200 or (1-y).sum()<200: return None,'insufficient_prior_attempts_or_nonattempts'
    with warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        m=LogisticRegression(C=1e6,max_iter=2000).fit(logit(p),y)
    if m.coef_[0,0]<=0: return None,'nonpositive_slope'
    return m,'logistic_recalibration'

def apply_calibration(m,p):
    return np.asarray(p) if m is None else m.predict_proba(logit(p))[:,1]

def training_mask(d,origin):
    return d['completion'].lt(origin) & d['start'].lt(d['completion'])

def calibration_pool(scores,origin,year):
    return scores[scores.completion.lt(origin)&scores.season.eq(year)&scores.raw.notna()]

def main(*, input_dir=None, output_dir=None, local_dir=None, verified_hashes=None, use_availability=False):
    global OUT, LOCAL
    if output_dir is not None: OUT=Path(output_dir)
    if local_dir is not None: LOCAL=Path(local_dir)
    input_dir=Path(input_dir) if input_dir is not None else ROOT/'data/processed/historical/development'
    OUT.mkdir(exist_ok=True); LOCAL.mkdir(exist_ok=True)
    assert not (ROOT/'data/historical_feed_manifest_2025.csv').exists()
    hashes={}
    frames=[]
    baseline=json.loads((ROOT/'results/recorded_attempt_baseline/provenance.json').read_text())
    expected_hashes=verified_hashes if verified_hashes is not None else baseline['inputs']
    for year in (2022,2023):
        path=input_dir/f'opportunities_{year}.csv.gz'
        hashes[str(year)]=hashlib.sha256(path.read_bytes()).hexdigest()
        assert hashes[str(year)]==expected_hashes[str(year)]
        frames.append(pd.read_csv(path,low_memory=False))
    d=pd.concat(frames,ignore_index=True)
    for c in ['history_frozen_before_game','runner_history_coverage_complete_since_2022_start','game_chronology_available']: assert d[c].eq(True).all()
    d['start']=pd.to_datetime(d.feed_game_start_utc,utc=True,format='mixed')
    d['completion']=pd.to_datetime(d['history_available_after_utc'] if use_availability else d.feed_completion_time_utc,utc=True,format='mixed')
    scores=d[['opportunity_id','game_pk','season',LABEL,'start','completion','terminal_window','runner_identity_changed_within_window','recorded_disengagements_at_open','runner_prior_all_regimes_eligible_opportunities']].copy()
    scores['raw']=np.nan; scores['prospective_calibrated']=np.nan
    scores['origin']=''; scores['calibration_status']='warmup_no_prediction'
    invalid=d.start.ge(d.completion)
    scores.loc[invalid,'calibration_status']='quarantined_invalid_game_chronology'
    d.loc[invalid,['opportunity_id','game_pk','start','completion']].to_csv(OUT/'chronology_quarantine.csv',index=False)
    origins=[]
    for origin in pd.date_range('2022-07-01','2023-10-01',freq='MS',tz='UTC'):
        mask=d.start.ge(origin)&d.start.lt(origin+pd.offsets.MonthBegin(1))&~invalid
        if not mask.any(): continue
        train=d[training_mask(d,origin)]
        pool=calibration_pool(scores,origin,origin.year)
        m=fit(train,'separate_history')
        cal,status=fit_calibration(pool.raw,pool[LABEL])
        p=predict(m,d[mask]); q=apply_calibration(cal,p)
        assert train.completion.max()<d.loc[mask,'start'].min()
        assert not set(train.game_pk)&set(d.loc[mask,'game_pk'])
        if len(pool): assert pool.completion.max()<d.loc[mask,'start'].min()
        scores.loc[mask,'raw']=p; scores.loc[mask,'prospective_calibrated']=q
        scores.loc[mask,'origin']=origin.isoformat(); scores.loc[mask,'calibration_status']=status
        record=dict(origin=origin.isoformat(),fit_n=len(train),fit_attempts=int(train[LABEL].sum()),fit_max_completion=train.completion.max().isoformat(),score_n=int(mask.sum()),score_attempts=int(d.loc[mask,LABEL].sum()),score_min_start=d.loc[mask,'start'].min().isoformat(),calibration_n=len(pool),calibration_attempts=int(pool[LABEL].sum()),calibration_max_completion=pool.completion.max().isoformat() if len(pool) else '',calibration_status=status,intercept=float(cal.intercept_[0]) if cal is not None else 0,slope=float(cal.coef_[0,0]) if cal is not None else 1)
        origins.append(record)
        joblib.dump(dict(base=m,calibrator=cal,provenance=record),LOCAL/f'model_{origin:%Y_%m}.joblib')
        print(origin.date(),int(mask.sum()),status,flush=True)
    scores.to_csv(LOCAL/'training_forward_scores.csv.gz',index=False)
    pd.DataFrame(origins).to_csv(OUT/'origins.csv',index=False)
    select=scores[scores.start.ge(pd.Timestamp('2023-07-01',tz='UTC'))&scores.raw.notna()]
    raw=metrics(select[LABEL],select.raw); calibrated=metrics(select[LABEL],select.prospective_calibrated)
    policy='logistic_recalibration' if calibrated['log_loss']<raw['log_loss'] and calibrated['brier']<=raw['brier'] else 'identity'
    final_pool=calibration_pool(scores,pd.Timestamp('2024-01-01',tz='UTC'),2023)
    final_cal,status=fit_calibration(final_pool.raw,final_pool[LABEL])
    assert status=='logistic_recalibration'
    decision=dict(selected_policy=policy,selection_raw=raw,selection_calibrated=calibrated,final_calibration_n=len(final_pool),final_calibration_attempts=int(final_pool[LABEL].sum()),final_intercept=float(final_cal.intercept_[0]),final_slope=float(final_cal.coef_[0,0]))
    (OUT/'policy.json').write_text(json.dumps(decision,indent=2)+'\n')
    # Selection is saved before any 2024 table is read in this stage.
    path=input_dir/'opportunities_2024.csv.gz'
    hashes['2024']=hashlib.sha256(path.read_bytes()).hexdigest()
    assert hashes['2024']==expected_hashes['2024']
    test=pd.read_csv(path,low_memory=False)
    base=fit(d[~invalid],'separate_history')
    p=predict(base,test)
    test['raw']=p; test['prospective_calibrated']=apply_calibration(final_cal,p)
    test['selected_probability']=test.prospective_calibrated if policy=='logistic_recalibration' else test.raw
    test[['opportunity_id','game_pk',LABEL,'raw','prospective_calibrated','selected_probability']].to_csv(LOCAL/'development_2024_scores.csv.gz',index=False)
    joblib.dump(dict(base=base,candidate_calibrator=final_cal,selected_policy=policy),LOCAL/'final_bundle.joblib')
    rows=[]; bins=[]; subgroups=[]; uncertainty=[]
    for split,frame in [('forward_2022',scores[scores.season.eq(2022)&scores.raw.notna()]),('forward_2023',scores[scores.season.eq(2023)&scores.raw.notna()]),('selection_2023',select),('development_2024',test)]:
        y=frame[LABEL].astype(int).to_numpy()
        for name in ['raw','prospective_calibrated']:
            p=frame[name].to_numpy(); a,b=calibration(y,p)
            rows.append(dict(split=split,model=name,n=len(frame),attempts=int(y.sum()),mean_prediction=float(p.mean()),observed_rate=float(y.mean()),calibration_intercept=a,calibration_slope=b,**metrics(y,p)))
            t=pd.DataFrame(dict(y=y,p=p,bin=pd.cut(p,BINS,include_lowest=True)))
            for label,g in t.groupby('bin',observed=False): bins.append(dict(split=split,model=name,bin=str(label),n=len(g),attempts=int(g.y.sum()),mean_prediction=g.p.mean(),observed_rate=g.y.mean()))
            axes={'history_depth':pd.cut(frame.runner_prior_all_regimes_eligible_opportunities,[-1,0,50,200,np.inf]).astype(str),'disengagements':frame.recorded_disengagements_at_open.astype(str),'terminal':frame.terminal_window.astype(str),'runner_change':frame.runner_identity_changed_within_window.astype(str)}
            for axis,v in axes.items():
                for value in sorted(v.unique()):
                    mask=v.eq(value).to_numpy()
                    subgroups.append(dict(split=split,model=name,subgroup=axis,value=value,n=int(mask.sum()),attempts=int(y[mask].sum()),mean_prediction=float(p[mask].mean()),observed_rate=float(y[mask].mean())))
        if split in ['selection_2023','development_2024']:
            codes,games=pd.factorize(frame.game_pk); rng=np.random.default_rng(20261115); differences=[]
            for _ in range(200):
                w=rng.multinomial(len(games),np.full(len(games),1/len(games)))[codes]
                r=metrics(y,frame.raw,w); c=metrics(y,frame.prospective_calibrated,w)
                differences.append([c[k]-r[k] for k in r])
            for j,k in enumerate(r):
                lo,hi=np.quantile(np.array(differences)[:,j],[.025,.975]); uncertainty.append(dict(split=split,metric=k,calibrated_minus_raw_lower=lo,calibrated_minus_raw_upper=hi))
    for name,records in [('metrics',rows),('calibration',bins),('subgroups',subgroups),('paired_bootstrap',uncertainty)]: pd.DataFrame(records).to_csv(OUT/f'{name}.csv',index=False)
    flow=scores.assign(scored=scores.raw.notna()).groupby(['season','scored','calibration_status']).agg(n=('opportunity_id','size'),games=('game_pk','nunique'),attempts=(LABEL,'sum'),terminal=('terminal_window','sum'),runner_change=('runner_identity_changed_within_window','sum'))
    flow.to_csv(OUT/'sample_flow.csv')
    hashes['protocol']=hashlib.sha256((ROOT/'docs/forward_threat_protocol.md').read_bytes()).hexdigest()
    hashes['script']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT/'provenance.json').write_text(json.dumps(dict(hashes=hashes,environment={k:baseline[k] for k in ['python','pandas','numpy','sklearn']}),indent=2)+'\n')
    print(json.dumps(decision,indent=2)); print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__': main()
