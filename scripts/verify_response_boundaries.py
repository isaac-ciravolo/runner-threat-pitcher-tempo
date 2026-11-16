"""Independently check raw response records against completed-play cutoffs."""
from collections import Counter

import pandas as pd

from scripts.pipeline_validation import require


def verify_response_boundaries(frame, feed):
    """Use raw event order and explicit links, without the grouping implementation."""
    plays = {}
    sequence = 0
    for play in feed['liveData']['plays']['allPlays']:
        events, identifiers = {}, {}
        for event in play.get('playEvents', []):
            sequence += 1
            require(event['index'] not in events, 'Duplicate raw event index')
            events[event['index']] = (event, sequence)
            if event.get('playId'):
                identifiers.setdefault(event['playId'], []).append(sequence)
        plays[play['about']['atBatIndex']] = (events, identifiers, play.get('runners', []))
    counts = Counter(windows=len(frame), response_actions=0, explicit_links=0, attempts=0,
                     eligible_movement_checks=0, outside_risk_movements=0)
    seen = set()
    for row in frame.itertuples(index=False):
        events, identifiers, movements = plays[row.at_bat_index]
        cutoff = int(row.feature_cutoff_game_sequence)
        close = events[int(row.close_event_index)][1]
        require(close > cutoff, 'Closing response precedes feature cutoff')
        attempts = 0
        action_ids = [] if pd.isna(row.response_action_ids) else str(row.response_action_ids).split('|')
        for action_id in filter(None, action_ids):
            require(action_id not in seen, 'Response action assigned twice')
            seen.add(action_id)
            parts = action_id.split('-')
            require(len(parts) >= 5 and parts[0] == 'A' and int(parts[1]) == feed['gamePk']
                    and int(parts[2]) == row.at_bat_index, 'Response action key mismatch')
            event, raw_sequence = events[int(parts[3])]
            require(raw_sequence > cutoff, 'Response annotation at/before cutoff')
            links = identifiers.get(event.get('actionPlayId'), [])
            require(len(links) <= 1, 'Nonunique explicit response link')
            effective = links[0] if links else raw_sequence
            require(cutoff < effective <= close, 'Linked response outside prediction window')
            counts['response_actions'] += 1
            counts['explicit_links'] += bool(links)
            kind = event.get('details', {}).get('eventType', '') or ''
            if parts[4].startswith('m'):
                reasons = [item.get('details', {}).get('movementReason', '') or '' for item in movements
                           if item.get('details', {}).get('playIndex') == int(parts[3])]
                require(bool(reasons), 'Movement-derived action has no source movement')
                attempts += any(reason.startswith(('r_stolen_base_', 'r_caught_stealing_')) for reason in reasons)
            else:
                defensive_record = event.get('type') in {'pickoff', 'stepoff'} or event.get('details', {}).get('code') == 'PSO'
                attempts += not defensive_record and kind.startswith(('stolen_base_', 'caught_stealing_'))
        require(attempts == row.recorded_steal_attempt_record_count, 'Attempt record accounting mismatch')
        counts['attempts'] += attempts
    for pa, (events, identifiers, movements) in plays.items():
        windows = frame[frame.at_bat_index.eq(pa)]
        checked = set()
        for item in movements:
            detail = item.get('details', {})
            reason = detail.get('movementReason', '') or ''
            steal = reason.startswith(('r_stolen_base_', 'r_caught_stealing_'))
            pickoff = reason.startswith('r_pickoff_')
            if not (steal or pickoff):
                continue
            index = detail.get('playIndex')
            require(index in events, 'Action movement has no raw event boundary')
            key = (index, detail.get('runner', {}).get('id'), steal)
            if key in checked:
                continue
            checked.add(key)
            event, sequence = events[index]
            links = identifiers.get(event.get('actionPlayId'), [])
            require(len(links) <= 1, 'Ambiguous movement parent')
            effective = links[0] if links else sequence
            matching = [row for row in windows.itertuples(index=False)
                        if row.feature_cutoff_game_sequence < effective <= events[int(row.close_event_index)][1]]
            require(len(matching) <= 1, 'Movement assigned to overlapping risk windows')
            if not matching:
                counts['outside_risk_movements'] += 1
                continue
            row = matching[0]
            ids = [] if pd.isna(row.response_action_ids) else str(row.response_action_ids).split('|')
            require(any(int(action.split('-')[3]) == index for action in ids if action),
                    'Eligible source movement is missing from response records')
            if steal:
                require(row.recorded_steal_attempt_record_count > 0, 'Eligible steal movement is not labeled')
            else:
                require(row.recorded_pitcher_pickoff_count + row.recorded_catcher_pickoff_count
                        + row.recorded_unknown_pickoff_count > 0, 'Eligible pickoff movement is not labeled')
            counts['eligible_movement_checks'] += 1
    return dict(counts)
