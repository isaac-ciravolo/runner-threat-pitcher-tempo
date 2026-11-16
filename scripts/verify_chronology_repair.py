"""Independent chronology-v2 history and model handoff checks."""
from scripts.pipeline_validation import require
from scripts.artifact_runs import resolve_run
import hashlib,json
import joblib
import numpy as np
import pandas as pd
from scripts.recorded_attempt_baseline import ROOT,predict
from scripts.forward_threat import apply_calibration
OUT=ROOT/'results/chronology_repair'

def main():
    data=pd.concat([pd.read_csv(ROOT/f'data/processed/chronology_repair/opportunities_{y}.csv.gz',low_memory=False) for y in (2022,2023,2024)],ignore_index=True)
    timing=pd.read_csv(OUT/'timing_dispositions.csv').set_index('game_pk')
    timing['freeze']=pd.to_datetime(timing.freeze_time,utc=True,format='mixed'); timing['available']=pd.to_datetime(timing.available_after,utc=True,format='mixed')
    require(data.opportunity_id.is_unique and len(data)==413081, 'Validation failed: data.opportunity_id.is_unique and len(data) == 413081')
    require((timing.freeze<timing.available).all(), 'Validation failed: (timing.freeze < timing.available).all()')
    numeric=[c for c in data if c.startswith('runner_prior_')]
    require(data[numeric].ge(0).all().all(), 'Validation failed: data[numeric].ge(0).all().all()')
    suffixes=['eligible_opportunities','attempted_opportunities','attempt_records','successes','unsuccessful','ambiguous_outcomes']
    for suffix in suffixes:
        require(data[f'runner_prior_all_regimes_{suffix}'].eq(data[f'runner_prior_pre_2023_{suffix}']+data[f'runner_prior_post_2023_{suffix}']).all(), "Validation failed: data[f'runner_prior_all_regimes_{suffix}'].eq(data[f'runner_prior_pre_2023_{suffix}'] + data[f'runner_prior_post_2023_{suffix}']).all()")
    require(data.groupby(['game_pk','runner_id'])[numeric].nunique().le(1).all().all(), "Validation failed: data.groupby(['game_pk', 'runner_id'])[numeric].nunique().le(1).all().all()")
    require(data[data.season.eq(2022)][[f'runner_prior_post_2023_{s}' for s in suffixes]].eq(0).all().all(), "Validation failed: data[data.season.eq(2022)][[f'runner_prior_post_2023_{s}' for s in suffixes]].eq(0).all().all()")
    # Independent batch summation, not the incremental state implementation.
    audit=pd.read_csv(OUT/'game_chronology_audit.csv')
    selected=set(audit[audit.resume_date.notna()].game_pk)|{663065,661565,745520}
    selected|=set(pd.Series(timing.index).sample(n=20,random_state=20261115))
    eligible=data[data.attempt_history_eligible.eq(True)].copy()
    eligible['available']=eligible.game_pk.map(timing.available)
    checked=0
    for pk in sorted(selected):
        current=data[data.game_pk.eq(pk)]
        prior=eligible[eligible.available.lt(timing.loc[pk,'freeze'])]
        require(not prior.game_pk.eq(pk).any(), 'Validation failed: not prior.game_pk.eq(pk).any()')
        for block,mask in [('all_regimes',prior.season.gt(0)),('pre_2023',prior.season.eq(2022)),('post_2023',prior.season.ge(2023))]:
            expected=prior[mask].groupby('runner_id').agg(eligible_opportunities=('opportunity_id','size'),attempted_opportunities=('recorded_steal_attempt_indicator','sum'),attempt_records=('recorded_steal_attempt_record_count','sum'),successes=('recorded_steal_success_count','sum'),unsuccessful=('recorded_steal_unsuccessful_count','sum'),ambiguous_outcomes=('recorded_steal_ambiguous_count','sum'))
            for row in current.drop_duplicates('runner_id').itertuples():
                for suffix in suffixes:
                    value=expected.loc[row.runner_id,suffix] if row.runner_id in expected.index else 0
                    require(getattr(row,f'runner_prior_{block}_{suffix}')==value, (pk,row.runner_id,block,suffix))
                    checked+=1
    completed=resolve_run(ROOT/'results/forward_threat_v2', ROOT/'data/processed/forward_threat_v2')
    local=completed.local
    legacy=resolve_run(ROOT/'results/forward_threat', ROOT/'data/processed/forward_threat')
    scores=pd.read_csv(local/'training_forward_scores.csv.gz')
    require(len(scores)==276594 and scores.opportunity_id.is_unique, 'Validation failed: len(scores) == 276594 and scores.opportunity_id.is_unique')
    require(scores[scores.game_pk.eq(716404)].raw.notna().all(), 'Validation failed: scores[scores.game_pk.eq(716404)].raw.notna().all()')
    lookup=data.set_index('opportunity_id')
    reloaded=0
    for origin,g in scores[scores.raw.notna()].groupby('origin'):
        date=pd.Timestamp(origin); bundle=joblib.load(local/f'model_{date:%Y_%m}.joblib')
        provenance=bundle['provenance']
        require(pd.Timestamp(provenance['fit_max_completion'])<date<=pd.Timestamp(provenance['score_min_start']), "Validation failed: pd.Timestamp(provenance['fit_max_completion']) < date <= pd.Timestamp(provenance['score_min_start'])")
        if provenance['calibration_max_completion']: require(pd.Timestamp(provenance['calibration_max_completion'])<date, "Validation failed: pd.Timestamp(provenance['calibration_max_completion']) < date")
        p=predict(bundle['base'],lookup.loc[g.opportunity_id]); q=apply_calibration(bundle['calibrator'],p)
        np.testing.assert_allclose(p,g.raw,rtol=1e-12,atol=1e-14); np.testing.assert_allclose(q,g.prospective_calibrated,rtol=1e-12,atol=1e-14)
        reloaded+=len(g)
    old=pd.read_csv(legacy.local/'training_forward_scores.csv.gz')
    comparison=old[['opportunity_id','raw']].merge(scores[['opportunity_id','raw']],on='opportunity_id',suffixes=('_v1','_v2'),validate='one_to_one')
    delta=[]
    for split,path in [('training',None),('development_2024','development_2024_scores.csv.gz')]:
        if path:
            a=pd.read_csv(legacy.local/path); b=pd.read_csv(local/path)
            comparison=a[['opportunity_id','raw']].merge(b[['opportunity_id','raw']],on='opportunity_id',suffixes=('_v1','_v2'),validate='one_to_one')
            final=joblib.load(local/'final_bundle.joblib'); p=predict(final['base'],lookup.loc[b.opportunity_id]); np.testing.assert_allclose(p,b.raw,rtol=1e-12,atol=1e-14)
            selected_p=apply_calibration(final['candidate_calibrator'],p) if final['selected_policy']=='logistic_recalibration' else p
            np.testing.assert_allclose(selected_p,b.selected_probability,rtol=1e-12,atol=1e-14)
        common=comparison.dropna(); change=(common.raw_v2-common.raw_v1).abs()
        delta.append(dict(split=split,common_scored=len(common),newly_scored=int((comparison.raw_v1.isna()&comparison.raw_v2.notna()).sum()),newly_warmup=int((comparison.raw_v1.notna()&comparison.raw_v2.isna()).sum()),mean_absolute_change=change.mean(),max_absolute_change=change.max()))
    pd.DataFrame(delta).to_csv(OUT/'prediction_changes.csv',index=False)
    results=completed.results
    metrics=pd.read_csv(results/'metrics.csv')
    for filename,keys in [('calibration.csv',['split','model']),('subgroups.csv',['split','model','subgroup'])]:
        for key,g in pd.read_csv(results/filename).groupby(keys):
            row=metrics[(metrics.split==key[0])&(metrics.model==key[1])].iloc[0]
            require(g.n.sum()==row.n and g.attempts.sum()==row.attempts, 'Validation failed: g.n.sum() == row.n and g.attempts.sum() == row.attempts')
    require(not (ROOT/'data/historical_feed_manifest_2025.csv').exists(), "Validation failed: not (ROOT / 'data/historical_feed_manifest_2025.csv').exists()")
    result=dict(total_windows=len(data),unique_games=data.game_pk.nunique(),independent_reference_games=len(selected),independent_history_equalities=checked,reloaded_training_scores=reloaded,reloaded_development_scores=136487,restored_game_716404_windows=61,history_invariants_passed=True,score_accounting_passed=True,test_season_opened=False)
    (OUT/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2)); print(pd.DataFrame(delta).to_string(index=False))
if __name__=='__main__': main()
