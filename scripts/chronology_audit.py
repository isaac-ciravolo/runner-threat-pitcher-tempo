"""Audit cached public-feed chronology without downloading or inspecting 2025."""
from scripts.pipeline_validation import require
from pathlib import Path
from datetime import datetime
import hashlib,json
import pandas as pd
from scripts.recorded_attempt_baseline import ROOT
OUT=ROOT/'results/chronology_repair'

def timestamp(value):
    if not value: return None
    try: return datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except ValueError: return None

def iso(value): return value.isoformat() if value else ''

def audit_feed(feed):
    dates=feed['gameData'].get('datetime',{})
    starts=[]; ends=[]; pitches=[]; inverted=0; missing=0
    plays=feed['liveData']['plays']['allPlays']
    for play in plays:
        about=play.get('about',{})
        a=timestamp(about.get('startTime')); b=timestamp(about.get('endTime'))
        if a: starts.append(a)
        if b: ends.append(b)
        for event in play.get('playEvents',[]):
            a=timestamp(event.get('startTime')); b=timestamp(event.get('endTime'))
            if a: starts.append(a)
            if b: ends.append(b)
            if a and b and a>b: inverted+=1
            if not a or not b: missing+=1
            if event.get('isPitch') and a: pitches.append(a)
    first=min(starts) if starts else None
    last=max(ends+starts) if ends or starts else None
    first_pitch=min(pitches) if pitches else None
    header=timestamp(dates.get('dateTime'))
    trailing=0
    for play in reversed(plays):
        if play.get('about',{}).get('isComplete'): break
        trailing+=1
    return dict(header_start=iso(header),original_date=dates.get('originalDate',''),resume_date=dates.get('resumeDate',''),resume_datetime=dates.get('resumeDateTime',''),resumed_from=dates.get('resumedFromDateTime',''),freeze_time=iso(first),last_observed_time=iso(last),first_pitch=iso(first_pitch),header_after_first_event_seconds=(header-first).total_seconds() if header and first else None,span_hours=(last-first).total_seconds()/3600 if last and first else None,pre_pitch_hours=(first_pitch-first).total_seconds()/3600 if first_pitch and first else None,inverted_events=inverted,missing_event_times=missing,trailing_incomplete_plays=trailing,header_after_last_event=bool(header and last and header>last),multi_date=bool(first and last and first.date()!=last.date()),resolved_bounds=bool(first and last and first_pitch and first<last and (first_pitch-first).total_seconds()<=36*3600))

def main():
    OUT.mkdir(exist_ok=True)
    rows=[]
    for year in (2022,2023,2024):
        manifest=pd.read_csv(ROOT/f'data/historical_feed_manifest_{year}.csv')
        for r in manifest[manifest.feed_eligible.eq(True)].itertuples(index=False):
            path=ROOT/r.cache_path; raw=path.read_bytes()
            require(hashlib.sha256(raw).hexdigest()==r.sha256, r.game_pk)
            feed=json.loads(raw)
            require(feed['gamePk']==r.game_pk, "Validation failed: feed['gamePk'] == r.game_pk")
            rows.append(dict(season=year,game_pk=r.game_pk,source_sha256=r.sha256,scheduled_start=r.scheduled_start_utc,old_start=r.feed_game_start_utc,old_completion=r.feed_completion_time_utc,**audit_feed(feed)))
            if len(rows)%500==0: print('Audited',len(rows),'cached feeds',flush=True)
    df=pd.DataFrame(rows)
    df.to_csv(OUT/'game_chronology_audit.csv',index=False)
    flagged=df[(df.resume_date.ne(''))|df.header_after_last_event|df.inverted_events.gt(0)|df.missing_event_times.gt(0)|df.trailing_incomplete_plays.gt(0)|df.span_hours.gt(18)|~df.resolved_bounds]
    flagged.to_csv(OUT/'flagged_games.csv',index=False)
    print('Games',len(df),'flagged',len(flagged),'unresolved bounds',int((~df.resolved_bounds).sum()))
    print(flagged[['season','game_pk','resume_date','span_hours','pre_pitch_hours','inverted_events','missing_event_times','trailing_incomplete_plays','header_after_last_event']].to_string(index=False))
if __name__=='__main__': main()
