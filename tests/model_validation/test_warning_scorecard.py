"""Synthetic operating metrics for the 30-calendar-day onset task."""

from datetime import date, datetime
import unittest

from models.validation.warning_scorecard import WarningCounts, WarningDay, warning_scorecard


def day(value):
    return date.fromisoformat("2024-" + value)


class WarningScorecardTests(unittest.TestCase):
    def score(self, rows, onsets, **kwargs):
        bounds = {"fold_start": day("01-01"), "fold_end": day("04-30"), "synthetic": True, **kwargs}
        return warning_scorecard(rows, onsets, **bounds)

    def test_day_burden_and_episode_recall_are_counted_separately(self):
        rows = [
            WarningDay(day("01-15"), 1, True, True),
            WarningDay(day("01-01"), 0, True, False),  # 31 days before first onset
            WarningDay(day("01-02"), 1, False, True),  # 30 days is in-window
            WarningDay(day("02-07"), 0, False, True),
            WarningDay(day("03-09"), 1, False, False),
        ]
        score = self.score(rows, [day("03-10"), day("02-01")])
        self.assertEqual((score.matched_origins, score.negative_origins), (5, 2))
        self.assertEqual(score.baseline, WarningCounts(1, 2, 1, 1))
        self.assertEqual(score.candidate, WarningCounts(1, 3, 1, 1))
        first, second = score.episodes
        self.assertEqual((first.baseline_lead_days, first.candidate_lead_days), (17, 30))
        self.assertEqual(first.matched_origins, 2)
        self.assertIsNone(second.candidate_lead_days)

    def test_one_warning_cannot_detect_two_nearby_episodes(self):
        score = self.score([
            WarningDay(day("01-15"), 1, False, True),
            WarningDay(day("02-03"), 1, False, False),
        ], [day("02-01"), day("02-10")])
        self.assertEqual(score.candidate, WarningCounts(0, 1, 1, 1))
        self.assertEqual([episode.matched_origins for episode in score.episodes], [1, 1])

    def test_incomplete_fold_windows_and_uncovered_episodes_are_not_misses(self):
        score = self.score([
            WarningDay(day("01-05"), 1, False, True),
        ], [day("01-10"), day("02-01"), day("02-15"), day("04-30")], fold_end=day("02-10"))
        self.assertEqual([episode.state for episode in score.episodes], ["fold_boundary", "no_matched_origins", "fold_boundary"])
        self.assertEqual(score.candidate, WarningCounts(0, 1, 0, 0))
        self.assertEqual(score.negative_origins, 0)

    def test_empty_matched_dates_do_not_create_false_misses(self):
        score = self.score([], [day("02-01")])
        self.assertEqual(score.matched_origins, 0)
        self.assertEqual(score.episodes[0].state, "no_matched_origins")
        self.assertEqual(score.candidate.missed_episodes, 0)

    def test_inconsistent_or_non_synthetic_inputs_are_rejected(self):
        onset = day("02-01")
        matched = WarningDay(day("01-02"), 1, False, False)
        for rows, onsets, options in (
            ([matched], [onset], {"synthetic": False}),
            ([matched, matched], [onset], {}),
            ([matched], [onset, onset], {}),
            ([matched], [], {}),
            ([matched], [onset], {"fold_start": day("01-03")}),
            ([WarningDay(onset, 0, False, False)], [onset], {}),
            ([WarningDay(day("01-02"), 1, None, False)], [onset], {}),
            ([WarningDay(datetime(2024, 1, 2), 1, False, False)], [onset], {}),
        ):
            with self.subTest(rows=rows, onsets=onsets, options=options), self.assertRaises(ValueError):
                self.score(rows, onsets, **options)


if __name__ == "__main__":
    unittest.main()
