"""Rebuild histories from validated game-level timing dispositions."""
from scripts.pipeline_validation import require
from scripts.source_snapshot import validate_source_snapshot
import hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from scripts.recorded_attempt_baseline import ROOT
from scripts.historical_processing import ForwardHistoryState
OUT=ROOT/'results/chronology_repair'
LOCAL=ROOT/'data/processed/chronology_repair'

def main():
    LOCAL.mkdir(exist_ok=True)
    audit=pd.read_csv(OUT/'game_chronology_audit.csv')
    disposition=pd.read_csv(OUT/'timing_dispositions.csv').set_index('game_pk')
    require(len(audit)==7289 and audit.resolved_bounds.all(), 'Validation failed: len(audit) == 7289 and audit.resolved_bounds.all()')
    require(set(audit.game_pk)==set(disposition.index), 'Validation failed: set(audit.game_pk) == set(disposition.index)')
    require(disposition.status.eq('resolved').all(), "Validation failed: disposition.status.eq('resolved').all()")
    frames=[]; original_hashes={}
    for year in (2022,2023,2024):
        path=ROOT/f'data/processed/historical/development/opportunities_{year}.csv.gz'
        original_hashes[str(year)]=hashlib.sha256(path.read_bytes()).hexdigest()
        frames.append(pd.read_csv(path,low_memory=False))
    original=pd.concat(frames,ignore_index=True)
    manifests=pd.concat([
        pd.read_csv(ROOT/f'data/historical_feed_manifest_{year}.csv')
        for year in (2022,2023,2024)
    ], ignore_index=True)
    validate_source_snapshot(original, audit, disposition.reset_index(),
                             manifests[manifests.feed_eligible.eq(True)])
    groups={int(k):g for k,g in original.groupby('game_pk',sort=False)}
    require(set(groups)==set(disposition.index), 'Validation failed: set(groups) == set(disposition.index)')
    state=ForwardHistoryState(); rebuilt=[]; changes=[]
    disposition['freeze']=pd.to_datetime(disposition.freeze_time,utc=True,format='mixed')
    disposition['available']=pd.to_datetime(disposition.available_after,utc=True,format='mixed')
    require((disposition.freeze<disposition.available).all(), 'Validation failed: (disposition.freeze < disposition.available).all()')
    for pk,row in disposition.sort_values(['freeze','game_pk']).iterrows():
        old=groups[int(pk)]
        state.release_completed_before(row.freeze)
        history={r:state.snapshot(r,coverage_complete=True) for r in old.runner_id.unique()}
        new_hist=pd.DataFrame([history[r] for r in old.runner_id],index=old.index)
        history_columns=list(new_hist.columns)
        new=old.drop(columns=history_columns).copy()
        new=pd.concat([new,new_hist],axis=1)
        new['legacy_feed_game_start_utc']=old.feed_game_start_utc
        new['legacy_feed_completion_time_utc']=old.feed_completion_time_utc
        new['feed_game_start_utc']=row.freeze.isoformat()
        new['last_observed_event_time_utc']=row.last_observed_time
        new['history_available_after_utc']=row.available.isoformat()
        new['chronology_version']='event_bounds_v2'
        new['history_frozen_before_game']=True
        new['runner_history_coverage_reason']='complete_collected_window_with_v2_availability'
        numeric=[c for c in history_columns if c.startswith('runner_prior_')]
        changed=(old[numeric].to_numpy()!=new[numeric].to_numpy()).any(axis=1)
        changes.append(dict(season=int(old.season.iloc[0]),game_pk=int(pk),n=len(old),changed_history_rows=int(changed.sum()),changed_start_rows=int(old.feed_game_start_utc.ne(row.freeze.isoformat()).sum()),max_abs_opportunity_change=int(np.abs(old.runner_prior_all_regimes_eligible_opportunities-new.runner_prior_all_regimes_eligible_opportunities).max())))
        require(new.opportunity_id.tolist()==old.opportunity_id.tolist(), 'Validation failed: new.opportunity_id.tolist() == old.opportunity_id.tolist()')
        rebuilt.append(new)
        if len(rebuilt)%1000==0: print('Rebuilt histories for',len(rebuilt),'games',flush=True)
        state.queue_game(season=int(old.season.iloc[0]),completion_time=row.available,frame=new)
    data=pd.concat(rebuilt,ignore_index=True)
    protected=[c for c in original if c not in set(history_columns+['feed_game_start_utc','runner_history_coverage_reason'])]
    a=original.set_index('opportunity_id').sort_index(); b=data.set_index('opportunity_id').sort_index()
    pd.testing.assert_frame_equal(a[[c for c in protected if c!='opportunity_id']],b[[c for c in protected if c!='opportunity_id']],check_dtype=False)
    hashes={}
    for year,g in data.groupby('season'):
        path=LOCAL/f'opportunities_{year}.csv.gz'; g.to_csv(path,index=False,compression='gzip')
        hashes[str(year)]=hashlib.sha256(path.read_bytes()).hexdigest()
    changes=pd.DataFrame(changes); changes.to_csv(OUT/'history_changes_by_game.csv',index=False)
    changes.groupby('season')[['n','changed_history_rows','max_abs_opportunity_change']].agg({'n':'sum','changed_history_rows':'sum','max_abs_opportunity_change':'max'}).to_csv(OUT/'history_change_summary.csv')
    (OUT/'repaired_provenance.json').write_text(json.dumps(dict(original_input_hashes=original_hashes,repaired_input_hashes=hashes,dispositions_sha256=hashlib.sha256((OUT/'timing_dispositions.csv').read_bytes()).hexdigest(),rows=len(data),protected_columns_verified=protected),indent=2)+'\n')
    print(changes.groupby('season')[['n','changed_history_rows']].sum().to_string())
if __name__=='__main__': main()
