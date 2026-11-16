"""Apply documented timing dispositions to the checksum-verified audit."""
import pandas as pd
from scripts.recorded_attempt_baseline import ROOT
OUT=ROOT/'results/chronology_repair'

def availability(row):
    last=pd.Timestamp(row['last_observed_time'])
    pk=int(row['game_pk'])
    if pk==716404: return pd.Timestamp('2023-10-05T04:00:00Z'),'official_disposition_day_end'
    if pk in (663065,661565): return last+pd.Timedelta(hours=24),'rain_advisory_plus_24h_assumption'
    if pk==745520: return last,'conservative_late_timestamp_not_verified_completion'
    if pd.notna(row.get('resume_date')): return last,'resumed_final_event_proxy'
    return last,'last_event_proxy'

def main():
    audit=pd.read_csv(OUT/'game_chronology_audit.csv')
    assert len(audit)==7289 and audit.resolved_bounds.all()
    assert set(audit[audit.trailing_incomplete_plays.gt(0)].game_pk)=={663065,661565}
    assert set(audit[audit.header_after_last_event].game_pk)=={716404}
    rows=[]
    for _,r in audit.iterrows():
        available,reason=availability(r)
        rows.append(dict(season=int(r.season),game_pk=int(r.game_pk),freeze_time=r.freeze_time,last_observed_time=r.last_observed_time,available_after=available.isoformat(),availability_basis=reason,status='resolved',source_sha256=r.source_sha256))
    pd.DataFrame(rows).to_csv(OUT/'timing_dispositions.csv',index=False)
    print(pd.DataFrame(rows).groupby('availability_basis').size().to_string())
if __name__=='__main__': main()
