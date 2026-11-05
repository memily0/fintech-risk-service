from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from models.validation.temporal import (
    build_complete_composite_stress,
    build_future_event_labels,
    temporal_training_mask,
)
from scripts import train_crisis_model as trainer


class CompositeStressTests(unittest.TestCase):
    def test_warm_up_or_missing_component_remains_unknown(self) -> None:
        composite = build_complete_composite_stress(
            {
                "a": pd.Series([None, 1.0, 2.0]),
                "b": pd.Series([0.0, None, 2.0]),
            },
            threshold=1.0,
        )

        self.assertEqual(composite.event.tolist(), [pd.NA, pd.NA, 1])
        self.assertTrue(pd.isna(composite.score.iloc[0]))
        self.assertTrue(pd.isna(composite.score.iloc[1]))

    def test_misaligned_component_indexes_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "identical indexes"):
            build_complete_composite_stress(
                {
                    "a": pd.Series([1.0], index=[0]),
                    "b": pd.Series([1.0], index=[1]),
                },
                threshold=1.0,
            )


class FutureEventTargetTests(unittest.TestCase):
    def test_complete_calendar_window_produces_binary_target(self) -> None:
        dates = pd.Series(pd.date_range("2026-01-01", periods=6, freq="D"))
        events = pd.Series([0, 0, 1, 0, 0, 0], dtype="Int64")

        labels = build_future_event_labels(dates, events, horizon_days=2)

        self.assertEqual(labels.target.tolist(), [1, 1, 0, 0, pd.NA, pd.NA])
        self.assertEqual(labels.complete_window.tolist(), [True, True, True, True, False, False])

    def test_unknown_event_never_becomes_negative(self) -> None:
        dates = pd.Series(pd.date_range("2026-01-01", periods=4, freq="D"))
        events = pd.Series([0, pd.NA, 0, 0], dtype="Int64")

        labels = build_future_event_labels(dates, events, horizon_days=2)

        self.assertTrue(pd.isna(labels.target.iloc[0]))
        self.assertFalse(labels.complete_window.iloc[0])

    def test_immature_tail_remains_unknown_even_if_observed_rows_exist(self) -> None:
        dates = pd.Series(pd.date_range("2026-01-01", periods=5, freq="D"))
        events = pd.Series([0, 0, 0, 1, 0], dtype="Int64")

        labels = build_future_event_labels(
            dates,
            events,
            horizon_days=2,
            outcomes_available_through="2026-01-04",
        )

        self.assertEqual(labels.target.tolist(), [0, 1, pd.NA, pd.NA, pd.NA])
        self.assertEqual(labels.mature.tolist(), [True, True, False, False, False])

    def test_missing_calendar_date_makes_window_unknown(self) -> None:
        dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-03", "2026-01-04"]))
        events = pd.Series([0, 0, 0], dtype="Int64")

        labels = build_future_event_labels(dates, events, horizon_days=2)

        self.assertTrue(pd.isna(labels.target.iloc[0]))

    def test_duplicate_or_unsorted_dates_are_rejected(self) -> None:
        events = pd.Series([0, 0], dtype="Int64")
        with self.assertRaisesRegex(ValueError, "unique"):
            build_future_event_labels(
                pd.Series(pd.to_datetime(["2026-01-01", "2026-01-01"])),
                events,
                horizon_days=1,
            )
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            build_future_event_labels(
                pd.Series(pd.to_datetime(["2026-01-02", "2026-01-01"])),
                events,
                horizon_days=1,
            )


class TemporalTrainingMaskTests(unittest.TestCase):
    def test_label_end_equal_to_or_after_cutoff_is_excluded(self) -> None:
        dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]))
        target = pd.Series([0, 1, 0], dtype="Int64")
        label_end = pd.Series(pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"]))

        mask = temporal_training_mask(
            dates,
            target,
            label_end,
            cutoff="2026-01-03",
        )

        self.assertEqual(mask.tolist(), [True, False, False])

    def test_unknown_target_is_excluded(self) -> None:
        dates = pd.Series(pd.to_datetime(["2026-01-01", "2026-01-02"]))
        target = pd.Series([pd.NA, 1], dtype="Int64")
        label_end = pd.Series(pd.to_datetime(["2026-01-02", "2026-01-03"]))

        mask = temporal_training_mask(
            dates,
            target,
            label_end,
            cutoff="2026-01-04",
        )

        self.assertEqual(mask.tolist(), [False, True])


class RecordingPipeline:
    """Estimator stub that records trainer inputs without fitting a model."""

    def __init__(self) -> None:
        self.fit_index: list[int] = []
        self.fit_target: list[int] = []

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "RecordingPipeline":
        self.fit_index = features.index.tolist()
        self.fit_target = target.tolist()
        return self

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        return np.tile([0.5, 0.5], (len(features), 1))


class TrainerTemporalIntegrationTests(unittest.TestCase):
    def test_trainer_keeps_stress_warm_up_unknown(self) -> None:
        row_count = 260
        values = pd.Series(np.arange(row_count, dtype=float))
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=row_count, freq="D"),
                "vix": values,
                "usd_volatility": values * 1.1,
                "imoex_volatility": values * 1.2,
                "imoex_drawdown": -(values * 0.01),
                "ofz_spread_10_2": -(values * 0.02),
            }
        )

        stress = trainer.build_stress_frame(frame)

        self.assertTrue(stress.loc[:251, "stress_score"].isna().all())
        self.assertTrue(stress.loc[:251, "stress_event"].isna().all())
        self.assertTrue(stress.loc[252:, "stress_event"].notna().all())

    def test_trainer_keeps_unknown_future_outcome_unknown(self) -> None:
        row_count = 100
        dates = pd.Series(pd.date_range("2026-01-01", periods=row_count, freq="D"))
        events = pd.Series(0, index=dates.index, dtype="Int64")
        events.iloc[1] = pd.NA
        source = pd.DataFrame({"date": dates})
        stress = pd.DataFrame(
            {
                "stress_score": pd.Series(0.0, index=dates.index),
                "stress_event": events,
            }
        )

        result = trainer.add_target_columns(source, stress)

        self.assertTrue(pd.isna(result.loc[0, "target_7d"]))
        self.assertTrue(result.loc[row_count - 7 :, "target_7d"].isna().all())

    def test_trainer_excludes_cutoff_boundary_and_unknown_from_stub_fit(self) -> None:
        row_count = 210
        dates = pd.Series(pd.date_range("2026-01-01", periods=row_count, freq="D"))
        target = pd.Series(np.arange(row_count) % 2, dtype="Int64")
        target.iloc[100] = pd.NA
        features = pd.DataFrame({"synthetic_feature": np.arange(row_count, dtype=float)})
        cutoff = dates.iloc[203]
        pipeline = RecordingPipeline()

        with patch.object(trainer, "make_pipeline", return_value=pipeline):
            metrics, predictions = trainer.evaluate_walk_forward(
                features,
                target,
                dates,
                [cutoff.isoformat()],
                horizon_days=2,
            )

        self.assertEqual(len(metrics), 1)
        self.assertEqual(max(pipeline.fit_index), 200)
        self.assertNotIn(100, pipeline.fit_index)
        self.assertNotIn(201, pipeline.fit_index)  # label_end == cutoff
        self.assertNotIn(202, pipeline.fit_index)  # label_end > cutoff
        self.assertEqual(len(pipeline.fit_index), 200)
        self.assertFalse(predictions.loc[203:].isna().any())


if __name__ == "__main__":
    unittest.main()
