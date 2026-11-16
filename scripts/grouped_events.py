"""Conservative exact-ID grouping of delayed runner-outcome annotations."""
from collections import defaultdict

from scripts.pipeline_validation import require


def grouping_plan(play):
    """Return child-index -> parent-index and unresolved evidence for one PA.

    Only a contiguous annotation group can be collapsed. Unrelated intervening
    events are retained and reported rather than assigned an invented order.
    """
    events = play.get('playEvents', [])
    indexes = [event['index'] for event in events]
    require(len(indexes) == len(set(indexes)), 'Duplicate event index')
    positions = {index: position for position, index in enumerate(indexes)}
    identifiers = defaultdict(list)
    movement_indexes = {item.get('details', {}).get('playIndex')
                        for item in play.get('runners', [])}
    for event in events:
        if event.get('playId'):
            identifiers[event['playId']].append(event['index'])
    candidates, unresolved = {}, []
    for event in events:
        index = event['index']
        kind = event.get('details', {}).get('eventType', '') or ''
        steal = kind.startswith(('stolen_base_', 'caught_stealing_'))
        catcher_throw = (event.get('type') == 'pickoff'
                         and event.get('details', {}).get('fromCatcher') is True
                         and bool(event.get('actionPlayId')))
        if event.get('isPitch') or not (steal or catcher_throw or (index in movement_indexes and event.get('actionPlayId'))):
            continue
        link = event.get('actionPlayId')
        matches = identifiers.get(link, []) if link else []
        reason = None
        if event.get('isSubstitution'):
            reason = 'linked_substitution'
        elif len(matches) != 1:
            reason = 'missing_or_nonunique_parent'
        elif positions[matches[0]] >= positions[index]:
            reason = 'parent_not_earlier'
        if reason:
            unresolved.append(dict(event_index=index, event_type=kind, reason=reason))
        else:
            candidates[index] = matches[0]
    mapping = {}
    parents = set(candidates.values())
    for parent in parents:
        children = [child for child, value in candidates.items() if value == parent]
        last = max(positions[child] for child in children)
        span = indexes[positions[parent] + 1:last + 1]
        if parent in candidates or any(candidates.get(index) != parent for index in span):
            for child in children:
                unresolved.append(dict(event_index=child, event_type=events[positions[child]].get('details', {}).get('eventType'),
                                       reason='interleaved_or_nested_group'))
        else:
            mapping.update({child: parent for child in children})
    return mapping, unresolved


def collapse_outcome_groups(feed, events, actions):
    """Collapse validated groups while preserving raw action identifiers.

    Raw extraction already computes every intermediate base state. The grouped
    parent keeps its pre-state and takes the final child's post-state. Source
    rows remain available in the raw cache and the returned key crosswalk.
    """
    result, action_result = events.copy(), actions.copy()
    result['group_end_game_sequence'] = result.game_sequence
    key_map = {}
    by_key = result.set_index('event_key', drop=False)
    drop_indexes = []
    post_columns = ['bases_after', 'runner_1b_after', 'runner_2b_after', 'runner_3b_after',
                    'feed_count_balls', 'feed_count_strikes', 'feed_count_outs',
                    'post_away_score', 'post_home_score']
    for play in feed['liveData']['plays']['allPlays']:
        pa = play['about']['atBatIndex']
        mapping, unresolved = grouping_plan(play)
        # Unlinked outcomes outside the first-only risk set cannot label a
        # first-only opportunity. Keep their source order; never invent a link.
        for issue in unresolved:
            raw = by_key.loc[f'{feed["gamePk"]}:{pa}:{issue["event_index"]}']
            require(issue['reason'] == 'missing_or_nonunique_parent'
                    and raw.bases_before != '1B' and raw.bases_after != '1B',
                    f'Unresolved eligible event grouping in {feed["gamePk"]}/{pa}: {issue}')
        parents = defaultdict(list)
        for child, parent in mapping.items():
            child_key = f'{feed["gamePk"]}:{pa}:{child}'
            parent_key = f'{feed["gamePk"]}:{pa}:{parent}'
            key_map[child_key] = parent_key
            parents[parent_key].append(child_key)
        for parent_key, children in parents.items():
            parent = by_key.loc[parent_key]
            child_rows = by_key.loc[children].sort_values('event_order')
            final = child_rows.iloc[-1]
            target_index = result.index[result.event_key.eq(parent_key)]
            require(len(target_index) == 1, 'Nonunique effective event')
            for column in post_columns:
                result.loc[target_index, column] = final[column]
            result.loc[target_index, 'group_end_game_sequence'] = final.game_sequence
            drop_indexes.extend(child_rows.index.tolist())
            for child_key in children:
                selected = action_result.event_key.eq(child_key)
                action_result.loc[selected, 'event_key'] = parent_key
                action_result.loc[selected, 'event_order'] = parent.event_order
    action_result['source_event_index'] = action_result.event_index
    action_result['effective_event_index'] = action_result.event_key.str.rsplit(':', n=1).str[-1].astype(int)
    result = result.loc[~result.event_key.isin(drop_indexes)].copy()
    require(result.event_key.is_unique and action_result.action_id.is_unique, 'Grouped key collision')
    require(set(action_result.action_id) == set(actions.action_id), 'Action loss during grouping')
    return result, action_result, key_map
