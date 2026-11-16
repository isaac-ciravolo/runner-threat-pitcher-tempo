"""Compact review evidence for timing and schedule edge cases."""
import json
import pandas as pd
from scripts.chronology_audit import timestamp
from scripts.recorded_attempt_baseline import ROOT
OUT=ROOT/'results/chronology_repair'

def main():
    flag=pd.read_csv(OUT/'flagged_games.csv'); rows=[]
    for r in flag.itertuples():
        feed=json.loads((ROOT/f'data/raw/historical/{r.season}/game_{r.game_pk}/current.json').read_bytes())
        for play in feed['liveData']['plays']['allPlays']:
            for e in play['playEvents']:
                a=timestamp(e.get('startTime')); b=timestamp(e.get('endTime'))
                if (a and b and a>b) or (r.game_pk==745520 and ((a and a.month>4) or (b and b.month>4))):
                    rows.append(dict(game_pk=r.game_pk,inning=play['about']['inning'],pa=play['about']['atBatIndex'],type=e.get('type'),event=e.get('details',{}).get('eventType'),start=e.get('startTime'),end=e.get('endTime'),is_pitch=e.get('isPitch'),description=e.get('details',{}).get('description')))
    pd.DataFrame(rows).to_csv(OUT/'anomalous_events.csv',index=False)
    frames=[]
    fields=['season','game_pk','rescheduled_from_date','rescheduled_date','resumed_from_date','resume_date','doubleheader_code','game_number']
    for year in (2022,2023,2024):
        d=pd.read_csv(ROOT/f'data/historical_feed_manifest_{year}.csv')
        frames.append(d[d.feed_eligible.eq(True)][fields])
    schedule=pd.concat(frames,ignore_index=True)
    edge=schedule[ schedule[['rescheduled_from_date','rescheduled_date','resumed_from_date','resume_date']].notna().any(axis=1)|schedule.doubleheader_code.ne('N')]
    audit=pd.read_csv(OUT/'game_chronology_audit.csv')
    edge.merge(audit[['game_pk','freeze_time','last_observed_time','header_after_first_event_seconds','resolved_bounds']],on='game_pk',validate='one_to_one').to_csv(OUT/'schedule_edge_audit.csv',index=False)
    print('Schedule edge games:',len(edge),'anomalous event records:',len(rows))
if __name__=='__main__': main()
