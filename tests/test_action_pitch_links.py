import unittest

from scripts.audit_action_pitch_links import linked_pitch_order
from scripts.pipeline_validation import ValidationError


class LinkTests(unittest.TestCase):
    def test_exact_link_only(self):
        events = [{'isPitch': True, 'playId': 'p'}, {'actionPlayId': 'p'}]
        self.assertEqual(linked_pitch_order(events, events[1]), 0)
        self.assertIsNone(linked_pitch_order(events, {}))
        self.assertIsNone(linked_pitch_order(events, {'actionPlayId': 'other'}))

    def test_duplicate_pitch_link_fails(self):
        with self.assertRaises(ValidationError):
            linked_pitch_order([{'isPitch': True, 'playId': 'p'}] * 2, {'actionPlayId': 'p'})
