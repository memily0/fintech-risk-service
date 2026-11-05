"""Optional offline suite; no fit, source reads, weights or private datasets."""

import unittest

import numpy as np
import pandas as pd

from models.validation import build_complete_composite_stress, build_future_event_labels, temporal_training_mask
from models.validation.product import COMPONENTS, prepare_validation, training_rows


class TemporalIntegrationTests(unittest.TestCase):
    def frame(self):
        values = [0., 0., 2., 0., 0., 0.]
        return pd.DataFrame({"date": pd.date_range("2026-01-01", periods=6, freq="D"), **{name: values.copy() for name in COMPONENTS}})

    def prepare(self, frame=None, **overrides):
        options = dict(data_snapshot_id="synthetic-temporal-001", horizon_days=2, threshold=1., outcomes_available_through="2026-01-06", synthetic=True)
        options.update(overrides)
        return prepare_validation(self.frame() if frame is None else frame, **options)

    def test_original_warmup_semantics_preserved(self):
        result = build_complete_composite_stress({"a": pd.Series([None, 1., 2.]), "b": pd.Series([0., None, 2.])}, threshold=1.)
        self.assertEqual(result.event.tolist(), [pd.NA, pd.NA, 1])

    def test_original_complete_calendar_labels(self):
        frame = self.frame()
        labels = build_future_event_labels(frame.date, pd.Series([0, 0, 1, 0, 0, 0], dtype="Int64"), horizon_days=2)
        self.assertEqual(labels.target.tolist(), [1, 1, 0, 0, pd.NA, pd.NA])

    def test_original_unknown_event_does_not_become_negative(self):
        labels = build_future_event_labels(self.frame().date, pd.Series([0, pd.NA, 0, 0, 0, 0], dtype="Int64"), horizon_days=2)
        self.assertTrue(pd.isna(labels.target.iloc[0]))

    def test_original_missing_date_remains_unknown(self):
        frame = self.frame().drop(index=1)
        labels = build_future_event_labels(frame.date, pd.Series(0, index=frame.index, dtype="Int64"), horizon_days=2)
        self.assertTrue(pd.isna(labels.target.iloc[0]))

    def test_original_equal_cutoff_is_excluded(self):
        dates = self.frame().date
        mask = temporal_training_mask(dates, pd.Series(0, index=dates.index, dtype="Int64"), dates + pd.Timedelta(days=2), cutoff="2026-01-05")
        self.assertEqual(mask.tolist(), [True, True, False, False, False, False])

    def test_original_misaligned_components_rejected(self):
        with self.assertRaises(ValueError):
            build_complete_composite_stress({"a": pd.Series([1.], index=[0]), "b": pd.Series([1.], index=[1])}, threshold=1.)

    def test_product_preparation_preserves_labels_and_identity(self):
        prepared = self.prepare()
        self.assertEqual(prepared.frame.target.tolist(), [1, 1, 0, 0, pd.NA, pd.NA])
        self.assertEqual(prepared.data_snapshot_id, "synthetic-temporal-001")
        self.assertFalse(prepared.model_quality_validated)
        self.assertTrue(prepared.synthetic)

    def test_training_boundary_applied_to_prepared_frame(self):
        rows = training_rows(self.prepare(), cutoff="2026-01-05")
        self.assertEqual(rows.index.tolist(), [0, 1])
        self.assertTrue((rows.label_end < pd.Timestamp("2026-01-05")).all())

    def test_no_mandatory_component_may_be_removed(self):
        with self.assertRaisesRegex(ValueError, "five"):
            self.prepare(self.frame().drop(columns=[COMPONENTS[0]]))

    def test_missing_component_does_not_become_no_event(self):
        frame = self.frame()
        frame.loc[1, COMPONENTS[0]] = np.nan
        result = self.prepare(frame).frame
        self.assertTrue(pd.isna(result.stress_event.iloc[1]))
        self.assertTrue(pd.isna(result.target.iloc[0]))

    def test_outcomes_asof_does_not_use_later_observed_rows(self):
        result = self.prepare(outcomes_available_through="2026-01-04").frame
        self.assertTrue(result.target.iloc[2:].isna().all())

    def test_invalid_thresholds_are_rejected_before_label_creation(self):
        for threshold in (True, float("nan"), float("inf"), "1"):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                self.prepare(threshold=threshold)

    def test_infinite_or_text_component_is_rejected(self):
        for value in (float("inf"), "1"):
            frame = self.frame().astype({COMPONENTS[0]: "object"})
            frame.loc[0, COMPONENTS[0]] = value
            with self.assertRaises(ValueError):
                self.prepare(frame)

    def test_intraday_or_timezone_dates_are_not_silently_normalized(self):
        for dates in (self.frame().date + pd.Timedelta(hours=12), self.frame().date.dt.tz_localize("UTC")):
            frame = self.frame()
            frame["date"] = dates
            with self.assertRaises(ValueError):
                self.prepare(frame)

    def test_duplicate_or_unsorted_origins_rejected(self):
        for frame in (self.frame().iloc[::-1], self.frame().assign(date=pd.Timestamp("2026-01-01"))):
            with self.assertRaises(ValueError):
                self.prepare(frame)

    def test_nondefault_index_does_not_realign_outcomes(self):
        frame = self.frame()
        frame.index = [10, 20, 30, 40, 50, 60]
        result = self.prepare(frame)
        self.assertEqual(result.frame.index.tolist(), frame.index.tolist())
        self.assertEqual(result.frame.target.tolist(), [1, 1, 0, 0, pd.NA, pd.NA])

    def test_real_or_unidentified_inputs_are_not_accepted_by_synthetic_bridge(self):
        for values in ({"synthetic": False}, {"synthetic": 1}, {"data_snapshot_id": ""}):
            with self.assertRaises(ValueError):
                self.prepare(**values)

    def test_invalid_horizons_are_rejected(self):
        for horizon in (True, 0, -1, 2.0):
            with self.assertRaises(ValueError):
                self.prepare(horizon_days=horizon)


if __name__ == "__main__":
    unittest.main()
