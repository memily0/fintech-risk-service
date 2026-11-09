"""Business-target semantics on invented data, not evidence of forecast skill."""

import unittest

import pandas as pd

from arcshift_v1.task_definition import TASK_DEFINITION
from models.validation.onset import LEGACY_ONSET_TARGET, prepare_onset_validation
from models.validation.product import COMPONENTS, prepare_validation, training_rows


class OnsetTaskTests(unittest.TestCase):
    def frame(self, periods=70):
        return pd.DataFrame({"date": pd.date_range("2026-01-01", periods=periods), **{name: [0.] * periods for name in COMPONENTS}})

    def prepare(self, frame=None, **overrides):
        options = dict(data_snapshot_id="synthetic-onset-001", threshold=1., outcomes_available_through="2026-03-11", synthetic=True)
        options.update(overrides)
        return prepare_onset_validation(self.frame() if frame is None else frame, **options)

    def event(self, frame, row):
        frame.loc[row, list(COMPONENTS)] = 2.

    def test_day_30_is_included_and_day_31_is_excluded(self):
        for offset, expected in ((1, 1), (30, 1), (31, 0)):
            frame = self.frame()
            self.event(frame, offset)
            with self.subTest(offset=offset):
                result = self.prepare(frame).frame
                self.assertEqual(result.target.iloc[0], expected)
                self.assertEqual(result.label_end.iloc[0], pd.Timestamp("2026-01-31"))

    def test_current_stress_is_not_a_future_onset_or_negative(self):
        frame = self.frame()
        self.event(frame, 0)
        result = self.prepare(frame).frame
        self.assertEqual(result.onset_origin_state.iloc[0], "already_in_stress")
        self.assertFalse(result.onset_risk_set.iloc[0])
        self.assertTrue(pd.isna(result.target.iloc[0]))

    def test_continuation_is_excluded_without_redefining_original_presence_target(self):
        frame = self.frame()
        self.event(frame, 0)
        self.event(frame, 1)
        original = prepare_validation(frame, data_snapshot_id="synthetic-old", horizon_days=30, threshold=1., outcomes_available_through="2026-03-11", synthetic=True)
        revised = self.prepare(frame)
        self.assertEqual(original.frame.target.iloc[0], 1)
        self.assertEqual(original.target_definition_id, "future_composite_stress_event_candidate.1")
        self.assertTrue(pd.isna(revised.frame.target.iloc[0]))
        self.assertEqual(revised.target_definition_id, LEGACY_ONSET_TARGET)
        self.assertNotEqual(revised.target_definition_id, TASK_DEFINITION.target_definition_id)

    def test_recovered_origin_can_warn_about_a_new_episode(self):
        frame = self.frame()
        self.event(frame, 0)
        self.event(frame, 20)
        result = self.prepare(frame).frame
        self.assertEqual(result.onset_origin_state.iloc[1], "at_risk")
        self.assertEqual(result.target.iloc[1], 1)

    def test_unknown_current_state_is_not_a_healthy_origin(self):
        frame = self.frame()
        frame.loc[0, COMPONENTS[0]] = float("nan")
        result = self.prepare(frame).frame
        self.assertEqual(result.onset_origin_state.iloc[0], "current_state_unknown")
        self.assertFalse(result.onset_risk_set.iloc[0])
        self.assertTrue(pd.isna(result.target.iloc[0]))

    def test_missing_future_component_or_calendar_date_leaves_target_unknown(self):
        unknown = self.frame()
        unknown.loc[10, COMPONENTS[0]] = float("nan")
        for frame in (unknown, self.frame().drop(index=10)):
            result = self.prepare(frame).frame
            self.assertTrue(result.onset_risk_set.iloc[0])
            self.assertTrue(pd.isna(result.target.iloc[0]))
            self.assertFalse(result.complete_window.iloc[0])

    def test_immature_outcome_cannot_use_later_rows(self):
        result = self.prepare(outcomes_available_through="2026-01-30").frame
        self.assertTrue(result.target.isna().all())
        self.assertFalse(result.mature.any())

    def test_training_excludes_active_stress_unknowns_and_cutoff_overlap(self):
        frame = self.frame()
        self.event(frame, 0)
        rows = training_rows(self.prepare(frame), cutoff="2026-02-10")
        self.assertNotIn(0, rows.index)
        self.assertNotIn(10, rows.index)  # label_end equals cutoff
        self.assertTrue(rows.onset_risk_set.all())
        self.assertTrue((rows.stress_event == 0).all())
        self.assertTrue(rows.target.notna().all())
        self.assertTrue((rows.label_end < pd.Timestamp("2026-02-10")).all())

    def test_snapshot_and_explicit_non_validation_flags_preserved(self):
        result = self.prepare()
        self.assertEqual(result.horizon_days, TASK_DEFINITION.primary_horizon_days)
        self.assertEqual(result.data_snapshot_id, "synthetic-onset-001")
        self.assertTrue(result.synthetic)
        self.assertFalse(result.model_quality_validated)

    def test_caller_cannot_override_approved_horizon(self):
        with self.assertRaises(TypeError):
            self.prepare(horizon_days=7)

    def test_real_inputs_remain_disallowed(self):
        with self.assertRaises(ValueError):
            self.prepare(synthetic=False)

    def test_input_frame_and_nondefault_index_are_preserved(self):
        frame = self.frame()
        frame.index = range(100, 170)
        before = frame.copy(deep=True)
        result = self.prepare(frame).frame
        pd.testing.assert_frame_equal(frame, before)
        self.assertEqual(result.index.tolist(), frame.index.tolist())
        self.assertEqual(result.target.iloc[0], 0)


if __name__ == "__main__":
    unittest.main()
