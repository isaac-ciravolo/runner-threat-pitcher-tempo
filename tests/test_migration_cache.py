import unittest

import pandas as pd

from scripts.rebuild_grouped_events import cache_signature, migrate_unaffected


class MigrationCacheTests(unittest.TestCase):
    def test_driver_changes_invalidate_cached_migrations(self):
        sources = {'scripts/rebuild_grouped_events.py': 'before', 'parser.py': 'stable'}
        original = cache_signature(sources, True)
        sources['scripts/rebuild_grouped_events.py'] = 'after'
        self.assertNotEqual(original, cache_signature(sources, True))
        self.assertNotEqual(cache_signature(sources, True), cache_signature(sources, False))
        self.assertEqual(cache_signature(sources, True), cache_signature(dict(reversed(list(sources.items()))), True))

    def test_migration_preserves_values_and_source(self):
        original = pd.DataFrame({'opportunity_id': ['G2-1-2-pre'], 'parser_version': ['old'],
                                 'recorded_steal_attempt_indicator': [False], 'runner_id': [42]})
        snapshot = original.copy(deep=True)
        result = migrate_unaffected(original)
        pd.testing.assert_frame_equal(original, snapshot)
        pd.testing.assert_frame_equal(result[['runner_id', 'recorded_steal_attempt_indicator']],
                                      original[['runner_id', 'recorded_steal_attempt_indicator']])
        self.assertEqual(result.opportunity_id.iloc[0], 'G3-1-2-pre')
        self.assertEqual(result.action_evidence_version.iloc[0], 'runner_movement_v3')

    def test_migration_rejects_already_migrated_rows(self):
        with self.assertRaises(ValueError):
            migrate_unaffected(pd.DataFrame({'opportunity_id': ['G3-1-2-pre']}))
