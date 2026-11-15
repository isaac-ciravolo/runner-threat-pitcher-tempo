import unittest

import pandas as pd

from scripts.video_validation import (
    ANNOTATION_COLUMNS,
    eligible_annotations,
    error_summary,
    evaluate_gate,
    join_annotations_to_feed,
    make_annotation_sheet,
)


def candidate_frame():
    return pd.DataFrame(
        [
            {
                "validation_id": "g1_pa2_e3_4",
                "sample_role": "primary",
                "second_annotation_requested": False,
                "game_pk": 1,
                "official_date": "2024-04-01",
                "venue": "Park",
                "at_bat_index": 2,
                "preceding_event_index": 3,
                "following_event_index": 4,
                "preceding_play_id": "p1",
                "following_play_id": "p2",
                "pitcher_name": "Pitcher",
                "batter_name": "Batter",
                "validation_stratum": "ordinary_bases_empty",
                "base_state": "bases_empty",
                "recorded_interruption_group": "ordinary",
            }
        ]
    )


def feed_intervals():
    return pd.DataFrame(
        [
            {
                "game_pk": 1,
                "at_bat_index": 2,
                "preceding_event_index": 3,
                "following_event_index": 4,
                "event_start_interval_seconds": 20.0,
            }
        ]
    )


class VideoValidationTests(unittest.TestCase):
    def test_annotation_sheet_is_blinded_to_feed_timing(self):
        sheet = make_annotation_sheet(candidate_frame())

        self.assertEqual(list(sheet.columns), ANNOTATION_COLUMNS)
        self.assertFalse(any(column.startswith("feed_") for column in sheet.columns))
        self.assertNotIn("event_start_interval_seconds", sheet.columns)

    def test_join_and_error_calculation(self):
        annotations = make_annotation_sheet(candidate_frame())
        annotations.loc[0, [
            "video_source",
            "video_url",
            "clip_start_offset",
            "clip_end_offset",
            "video_access_date_utc",
            "continuity_status",
            "continuity_evidence",
            "timebase_type",
            "release_1_video_seconds",
            "release_2_video_seconds",
            "timing_uncertainty_seconds",
            "observed_interruption_type",
            "selected_for_timing",
            "usable_for_timing",
            "annotator",
            "annotation_date_utc",
        ]] = [
            "Public continuous broadcast",
            "https://example.test/video",
            "00:01:40.00",
            "00:02:00.00",
            "2026-11-15T00:00:00Z",
            "continuous_verified",
            "Continuous clock and audio",
            "player_seconds_0.01",
            "100.0",
            "119.8",
            "0.02",
            "none_observed",
            "true",
            "true",
            "Reviewer",
            "2026-11-15T00:00:00Z",
        ]

        joined = join_annotations_to_feed(annotations, candidate_frame(), feed_intervals())
        eligible, excluded = eligible_annotations(joined)
        summary = error_summary(eligible).iloc[0]

        self.assertEqual(len(excluded), 0)
        self.assertAlmostEqual(eligible["derived_video_interval_seconds"].iloc[0], 19.8)
        self.assertAlmostEqual(eligible["signed_error_seconds"].iloc[0], 0.2)
        self.assertAlmostEqual(eligible["absolute_error_seconds"].iloc[0], 0.2)
        self.assertAlmostEqual(summary["mean_absolute_error"], 0.2)
        self.assertAlmostEqual(summary["median_signed_error"], 0.2)

    def test_excluded_or_discontinuous_annotation_is_not_analyzed(self):
        annotations = make_annotation_sheet(candidate_frame())
        annotations.loc[0, [
            "continuity_status",
            "timebase_type",
            "release_1_video_seconds",
            "release_2_video_seconds",
            "timing_uncertainty_seconds",
            "selected_for_timing",
            "usable_for_timing",
            "exclusion_reason",
            "annotator",
            "annotation_date_utc",
        ]] = [
            "edited_or_discontinuous",
            "player_seconds_0.01",
            "1.0",
            "20.0",
            "0.02",
            "true",
            "true",
            "edited between pitches",
            "Reviewer",
            "2026-11-15T00:00:00Z",
        ]

        joined = join_annotations_to_feed(annotations, candidate_frame(), feed_intervals())
        eligible, excluded = eligible_annotations(joined)

        self.assertTrue(eligible.empty)
        self.assertEqual(len(excluded), 1)

    def test_unknown_annotation_id_is_rejected(self):
        annotations = make_annotation_sheet(candidate_frame())
        annotations.loc[0, "validation_id"] = "unknown"

        with self.assertRaisesRegex(ValueError, "unknown validation_id"):
            join_annotations_to_feed(annotations, candidate_frame(), feed_intervals())

    def test_inconsistent_video_routes_are_not_analyzed(self):
        annotations = make_annotation_sheet(candidate_frame())
        annotations.loc[0, [
            "video_source", "video_url", "clip_start_offset", "clip_end_offset",
            "video_access_date_utc", "continuity_status", "continuity_evidence",
            "timebase_type", "video_timebase_fps", "release_1_video_seconds",
            "release_2_video_seconds", "release_1_frame", "release_2_frame",
            "timing_uncertainty_seconds", "observed_interruption_type",
            "selected_for_timing", "usable_for_timing", "annotator", "annotation_date_utc",
        ]] = [
            "Public continuous broadcast", "https://example.test/video", "00:00:10", "00:00:30",
            "2026-11-15T00:00:00Z", "continuous_verified", "Continuous clock and audio",
            "verified_30_fps", "30", "10.0", "30.0", "300", "930", "0.02",
            "none_observed", "true", "true", "Reviewer", "2026-11-15T00:00:00Z",
        ]

        joined = join_annotations_to_feed(annotations, candidate_frame(), feed_intervals())
        eligible, excluded = eligible_annotations(joined)

        self.assertTrue(eligible.empty)
        self.assertEqual(len(excluded), 1)
        self.assertAlmostEqual(joined["interval_consistency_difference"].iloc[0], 1.0)

    def test_empty_annotations_leave_gate_pending(self):
        result = evaluate_gate(pd.DataFrame())

        self.assertEqual(result.outcome, "validation_pending")
        self.assertEqual(result.validated_scope, "none")

    def test_secondary_round_is_separate_from_primary_analysis(self):
        annotations = make_annotation_sheet(candidate_frame())
        annotations.loc[0, [
            "video_source",
            "video_url",
            "clip_start_offset",
            "clip_end_offset",
            "video_access_date_utc",
            "continuity_status",
            "continuity_evidence",
            "timebase_type",
            "release_1_video_seconds",
            "release_2_video_seconds",
            "timing_uncertainty_seconds",
            "observed_interruption_type",
            "selected_for_timing",
            "usable_for_timing",
            "annotator",
            "annotation_round",
            "annotation_date_utc",
        ]] = [
            "Public continuous broadcast",
            "https://example.test/video",
            "00:00:10.00",
            "00:00:30.00",
            "2026-11-15T00:00:00Z",
            "continuous_verified",
            "Continuous clock and audio",
            "player_seconds_0.01",
            "10.0",
            "29.9",
            "0.02",
            "none_observed",
            "true",
            "true",
            "Second reviewer",
            "independent_second",
            "2026-11-15T00:00:00Z",
        ]

        joined = join_annotations_to_feed(annotations, candidate_frame(), feed_intervals())
        primary, _ = eligible_annotations(joined)
        secondary, _ = eligible_annotations(
            joined,
            annotation_rounds=("independent_second", "repeat_same_reviewer"),
        )

        self.assertTrue(primary.empty)
        self.assertEqual(len(secondary), 1)


if __name__ == "__main__":
    unittest.main()
