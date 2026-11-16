"""Freeze pitcher identity from starters and ordered substitution records."""
from scripts.pipeline_validation import require


def pitcher_timeline(feed):
    teams = feed['liveData']['boxscore']['teams']
    require(all(teams[side].get('pitchers') for side in ('home', 'away')), 'Missing starting pitcher order')
    current = {'top': int(teams['home']['pitchers'][0]), 'bottom': int(teams['away']['pitchers'][0])}
    snapshots = {0: current.copy()}
    events, substitutions = {}, []
    sequence = 0
    for play in feed['liveData']['plays']['allPlays']:
        pa = play['about']['atBatIndex']
        half = play['about']['halfInning']
        for order, event in enumerate(play.get('playEvents', [])):
            sequence += 1
            kind = event.get('details', {}).get('eventType')
            position = str(event.get('position', {}).get('code', ''))
            pitcher_change = kind == 'pitching_substitution' or (kind == 'defensive_switch' and position == '1')
            batter_change = kind == 'offensive_substitution' and position == '11'
            if pitcher_change:
                player = event.get('player', {}).get('id')
                require(player is not None, 'Pitcher substitution has no identity')
                current[half] = int(player)
            snapshots[sequence] = current.copy()
            events[(pa, order)] = sequence
            if pitcher_change or batter_change:
                substitutions.append((pa, order, pitcher_change, batter_change))
        if play.get('playEvents'):
            require(current[half] == play['matchup']['pitcher']['id'],
                    f'Pitcher timeline disagrees with final PA identity: {feed["gamePk"]}/{pa}')
    return snapshots, events, substitutions


def repair_opening_identities(frame, feed):
    snapshots, event_sequences, substitutions = pitcher_timeline(feed)
    result = frame.copy()
    result['legacy_opening_pitcher_id'] = frame.pitcher_id
    names = {int(person['id']): person.get('fullName', str(person['id']))
             for person in feed['gameData']['players'].values()}
    changed = 0
    for index, row in frame.iterrows():
        cutoff = int(row.feature_cutoff_game_sequence)
        require(cutoff in snapshots, 'Feature cutoff outside source event sequence')
        require(event_sequences[(row.at_bat_index, int(row.close_event_order))] > cutoff,
                'Response does not follow feature cutoff')
        pitcher = snapshots[cutoff][row.half_inning]
        result.at[index, 'pitcher_id'] = pitcher
        result.at[index, 'pitcher_name'] = names.get(pitcher, str(pitcher))
        changed += int(pitcher != row.pitcher_id)
        in_window = [item for item in substitutions if item[0] == row.at_bat_index
                     and row.feature_cutoff_event_order < item[1] <= row.close_event_order]
        pitcher_change = any(item[2] for item in in_window)
        batter_change = any(item[3] for item in in_window)
        result.at[index, 'pitcher_identity_changed_within_window'] = pitcher_change
        result.at[index, 'batter_identity_changed_within_window'] = batter_change
        eligible = bool(row.attempt_history_eligible and not pitcher_change and not batter_change)
        result.at[index, 'attempt_history_eligible'] = eligible
        result.at[index, 'conditional_success_history_eligible'] = bool(
            eligible and row.recorded_steal_attempt_record_count == 1
            and row.recorded_steal_outcome_class in {'recorded_success', 'recorded_unsuccessful'})
        reasons = [] if not isinstance(row.history_count_exclusion_reason, str) else row.history_count_exclusion_reason.split('|')
        reasons = [reason for reason in reasons if reason not in {'pitcher_changed', 'batter_changed'}]
        if pitcher_change:
            reasons.append('pitcher_changed')
        if batter_change:
            reasons.append('batter_changed')
        result.at[index, 'history_count_exclusion_reason'] = '|'.join(reasons)
    result['opening_pitcher_assignment_method'] = 'starting_pitcher_order_plus_event_substitutions'
    result['batter_identity_use'] = 'final_PA_metadata_not_permitted_as_opening_predictor'
    require(result.pitcher_id.notna().all(), 'Missing corrected pitcher identity')
    return result, changed
