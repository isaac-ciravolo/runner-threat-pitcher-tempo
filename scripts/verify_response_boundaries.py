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
        plays[play['about']['atBatIndex']] = (events, identifiers)
    counts = Counter(windows=len(frame), response_actions=0, explicit_links=0, attempts=0)
    seen = set()
    for row in frame.itertuples(index=False):
        events, identifiers = plays[row.at_bat_index]
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
            attempts += kind.startswith(('stolen_base_', 'caught_stealing_'))
        require(attempts == row.recorded_steal_attempt_record_count, 'Attempt record accounting mismatch')
        counts['attempts'] += attempts
    return dict(counts)
