"""Identify runner-specific action evidence attached to existing play events."""


def movement_action_type(reason):
    reason = reason or ''
    if reason.startswith('r_pickoff_'):
        return 'pickoff_throw'
    if reason.startswith(('r_stolen_base_', 'r_caught_stealing_')):
        return 'steal_attempt'
    if reason == 'r_balk':
        return 'balk'
    return None


def movement_evidence(movements):
    """Exclude accompanying advances from identifying the acting runner."""
    relevant = [item for item in movements
                if movement_action_type(item.get('details', {}).get('movementReason'))]
    kinds = {movement_action_type(item.get('details', {}).get('movementReason')) for item in relevant}
    actors = {item.get('details', {}).get('runner', {}).get('id') for item in relevant}
    # Retain the complete path of an identified actor, including a later out.
    paths = [item for item in movements if item.get('details', {}).get('runner', {}).get('id') in actors]
    return kinds, paths
