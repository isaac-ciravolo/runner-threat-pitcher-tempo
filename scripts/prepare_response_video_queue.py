"""Prepare an auditable stratified video queue; never manufacture annotations."""
import pandas as pd
from scripts.recorded_attempt_baseline import ROOT
from scripts.pipeline_validation import require

def main():
    frames=[]
    for year in (2023,2024):
        d=pd.read_csv(ROOT/f'data/processed/chronology_repair/opportunities_{year}.csv.gz',low_memory=False)
        d['action_interruption']=d.recorded_action_record_count.gt(0)
        d['stratum']=d[['season','recorded_pitcher_pickoff_indicator','recorded_catcher_pickoff_indicator','recorded_unknown_pickoff_indicator','terminal_window','open_timing','action_interruption']].astype(str).agg('|'.join,axis=1)
        frames.append(d)
    d=pd.concat(frames,ignore_index=True); samples=[]
    for stratum,g in d.groupby('stratum',sort=True):
        selected=g.sample(n=min(5,len(g)),random_state=20261115).copy()
        selected['stratum_population']=len(g); selected['stratum_selected']=len(selected)
        selected['inclusion_probability']=len(selected)/len(g)
        samples.append(selected)
    queue=pd.concat(samples,ignore_index=True)
    require(queue.opportunity_id.is_unique,'Duplicate video opportunities')
    columns=['opportunity_id','game_pk','season','at_bat_index','inning','half_inning','pitcher_id','runner_id','open_timing','open_anchor','close_event_index','terminal_window','recorded_pitcher_pickoff_indicator','recorded_catcher_pickoff_indicator','recorded_unknown_pickoff_indicator','action_interruption','stratum','stratum_population','stratum_selected','inclusion_probability']
    queue=queue[columns]
    queue['review_status']='unreviewed'; queue['video_url']=''; queue['reviewer']=''; queue['observed_pitcher_pickoff']=''; queue['continuity_verified']=''; queue['notes']=''
    output=ROOT/'results/pitcher_response_video_queue.csv'
    require(not output.exists(),'Refusing to overwrite an existing review queue')
    queue.to_csv(output,index=False)
    print('Prepared',len(queue),'unreviewed windows in',queue.stratum.nunique(),'strata')
if __name__=='__main__': main()
