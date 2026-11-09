"""Frozen measurement semantics on invented values and invented calendars."""

from dataclasses import FrozenInstanceError
import unittest

import numpy as np
import pandas as pd

from arcshift_v1.stress_definition import MEASUREMENT_SHA256, STRESS_DEFINITION as POLICY
from models.validation.evaluation import FeatureSnapshot, fold_training_batch
from models.validation.measurement import _cutoffs, domestic_event, measure_stress, prepared_onset, prior_midrank
from models.validation.product import training_rows


class RecordingEstimator:
    def __init__(self):
        self.fit_index = None
        self.fit_target = None

    def fit(self, features, target):
        self.fit_index = features.index.copy()
        self.fit_target = target.copy()
        return self


class StressMeasurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dates = pd.date_range("2020-01-01", periods=650)
        cls.calendar = pd.DataFrame({"date": cls.dates, "known_at": "2019-01-01T00:00:00Z", **{item.market: "open" for item in POLICY.inputs}})
        rows = []
        for item, value in zip(POLICY.inputs, (75., 100., 10.), strict=True):
            for day in cls.dates:
                rows.append(dict(date=day, series_id=item.series_id, resource_id=item.resource_id, units=item.units, value=value, received_at=(day + pd.Timedelta(hours=20)).tz_localize("Europe/Moscow").isoformat(), published_at=None, receipt_sha256="a" * 64, quality="observed", is_synthetic=True))
        cls.observations = pd.DataFrame(rows)

    def run_measurement(self, observations=None, calendar=None, **overrides):
        options = dict(data_snapshot_id="synthetic-measurement-001", calendar_snapshot_id="invented-calendar-001", available_through="2023-01-01T12:00:00+03:00", synthetic=True)
        options.update(overrides)
        return measure_stress(self.observations if observations is None else observations, self.calendar if calendar is None else calendar, **options)

    def row(self, market, position):
        return list(POLICY.mandatory_segments).index(market) * len(self.dates) + position

    def test_policy_is_frozen_and_not_economic_validation(self):
        self.assertEqual(len(MEASUREMENT_SHA256), 64)
        self.assertFalse(POLICY.empirical_validity_established)
        self.assertFalse(POLICY.source_admission_complete)
        with self.assertRaises(FrozenInstanceError):
            POLICY.segment_threshold = .8

    def test_rank_excludes_current_and_requires_252_prior_values(self):
        values = pd.Series([0.] * 252 + [100.])
        rank = prior_midrank(values)
        self.assertTrue(rank.iloc[:252].isna().all())
        self.assertEqual(rank.iloc[252], 1.)

    def test_constant_history_midrank_is_half_not_extreme_stress(self):
        self.assertEqual(prior_midrank(pd.Series([0.] * 253)).iloc[-1], .5)

    def test_rank_window_is_bounded_and_unknowns_not_counted_as_history(self):
        values = pd.Series([100.] * 800 + [0.] * 756 + [50.])
        self.assertEqual(prior_midrank(values).iloc[-1], 1.)
        self.assertTrue(pd.isna(prior_midrank(pd.Series([np.nan] * 300 + [1.])).iloc[-1]))

    def test_two_distinct_segments_required_at_inclusive_threshold(self):
        frame = pd.DataFrame([[.9, .9, .5], [1., .5, .5], [.8999, .9, .5]], columns=POLICY.mandatory_segments)
        intensity, event = domestic_event(frame)
        self.assertEqual(event.tolist(), [1, 0, 0])
        self.assertAlmostEqual(intensity.iloc[0], 2.3 / 3)

    def test_two_positive_votes_do_not_override_unknown_third_segment(self):
        frame = pd.DataFrame([[1., 1., np.nan]], columns=POLICY.mandatory_segments)
        intensity, event = domestic_event(frame)
        self.assertTrue(pd.isna(event.iloc[0]))
        self.assertTrue(pd.isna(intensity.iloc[0]))

    def test_extra_or_invalid_segments_cannot_change_weights(self):
        frame = pd.DataFrame([[.5, .5, .5]], columns=POLICY.mandatory_segments)
        for changed in (frame.assign(vix=1.), frame.assign(fx=2.), frame.assign(fx=True)):
            with self.assertRaises(ValueError):
                domestic_event(changed)

    def test_flat_market_has_explicit_warmup_then_known_nonstress(self):
        result = self.run_measurement()
        self.assertTrue(result.frame.stress_event.iloc[:503].isna().all())
        self.assertEqual(result.frame.stress_event.iloc[503], 0)
        self.assertEqual(result.frame.stress_intensity.iloc[503], .5)
        self.assertFalse(result.empirical_validity_established)

    def test_raw_formulas_use_native_log_returns_and_percentage_point_change(self):
        rows = self.observations.copy()
        for position in range(630, 650):
            rows.loc[self.row("fx", position), "value"] = 75 * (1.1 if position % 2 else 1.)
        rows.loc[self.row("rates", 649), "value"] = 12.
        result = self.run_measurement(rows)
        native = result.native_frames["fx"]
        expected = np.log(native.value).diff().iloc[-20:].std(ddof=1)
        self.assertAlmostEqual(native.volatility.iloc[-1], expected)
        self.assertEqual(result.native_frames["rates"].yield_increase.iloc[-1], 2.)

    def test_equity_drawdown_is_trailing_252_not_all_history_peak(self):
        rows = self.observations.copy()
        rows.loc[self.row("equity", 0), "value"] = 1000.
        result = self.run_measurement(rows)
        self.assertEqual(result.native_frames["equity"].drawdown.iloc[-1], 0.)

    def test_vix_alone_never_changes_domestic_target(self):
        baseline = self.run_measurement()
        extra = self.observations.iloc[[0]].copy()
        extra["series_id"] = "global.volatility.cboe.vix.close"
        extra["value"] = 1e9
        changed = self.run_measurement(pd.concat([self.observations, extra], ignore_index=True))
        pd.testing.assert_frame_equal(baseline.frame, changed.frame)

    def test_equity_two_indicators_count_as_only_one_segment(self):
        rows = self.observations.copy()
        rows.loc[self.row("equity", 649), "value"] = 10.
        result = self.run_measurement(rows).frame
        self.assertEqual(result.equity.iloc[-1], 1.)
        self.assertEqual(result.stress_event.iloc[-1], 0)

    def test_two_domestic_shocks_trigger_event_and_exclude_active_origin(self):
        rows = self.observations.copy()
        rows.loc[self.row("equity", 600), "value"] = 10.
        rows.loc[self.row("fx", 600), "value"] = 150.
        result = self.run_measurement(rows).frame
        self.assertEqual(result.stress_event.iloc[600], 1)
        self.assertTrue(result.episode_start.iloc[600])
        self.assertEqual(result.onset_origin_state.iloc[600], "already_in_stress")
        self.assertTrue(pd.isna(result.target.iloc[600]))
        self.assertEqual(result.target.iloc[570], 1)  # event is on day 30
        self.assertEqual(result.target.iloc[569], 0)  # event is on day 31

    def test_cutoff_uses_local_wall_clock_even_across_historical_dst(self):
        dates = pd.to_datetime(["2010-03-28", "2010-10-31"])
        self.assertEqual(_cutoffs(dates).tz_convert(POLICY.timezone).hour.tolist(), [9, 9])

    def test_current_measurement_never_uses_same_origin_day_session(self):
        result = self.run_measurement().frame
        self.assertEqual(result.date.iloc[-1], self.dates[-1] + pd.Timedelta(days=1))
        self.assertLess(result.fx_reference_date.iloc[-1], result.date.iloc[-1])
        self.assertEqual(result.forecast_cutoff.iloc[-1].tz_convert("Europe/Moscow").hour, 9)

    def test_late_receipt_does_not_repair_frozen_native_value(self):
        rows = self.observations.copy()
        row = self.row("fx", 600)
        rows.loc[row, "received_at"] = (self.dates[600] + pd.Timedelta(days=1, hours=10)).tz_localize("Europe/Moscow").isoformat()
        result = self.run_measurement(rows)
        self.assertTrue(pd.isna(result.native_frames["fx"].value.iloc[600]))
        self.assertTrue(pd.isna(result.frame.stress_event.iloc[600]))

    def test_latest_revision_before_deadline_used_later_revision_ignored(self):
        extra = self.observations.iloc[[self.row("fx", 600)]].copy()
        extra["value"] = 90.
        extra["receipt_sha256"] = "b" * 64
        extra["received_at"] = (self.dates[600] + pd.Timedelta(hours=21)).tz_localize("Europe/Moscow").isoformat()
        later = extra.copy()
        later["value"] = 1000.
        later["received_at"] = "2023-01-01T00:00:00Z"
        result = self.run_measurement(pd.concat([self.observations, extra, later], ignore_index=True))
        self.assertEqual(result.native_frames["fx"].value.iloc[600], 90.)
        self.assertEqual(result.native_frames["fx"].receipt_sha256.iloc[600], "b" * 64)

    def test_future_observations_do_not_change_past_measurements(self):
        result = self.run_measurement()
        subset = self.run_measurement(available_through="2021-07-01T09:00:00+03:00")
        mask = subset.frame.forecast_cutoff <= pd.Timestamp("2021-07-01T09:00:00+03:00")
        columns = ["date", "fx", "equity", "rates", "stress_event", "stress_intensity"]
        pd.testing.assert_frame_equal(result.frame.loc[mask, columns], subset.frame.loc[mask, columns])

    def test_cutoff_boundary_before_and_at_0900(self):
        for time, known in (("08:59:59", False), ("09:00:00", True)):
            as_of = self.dates[-1] + pd.Timedelta(days=1)
            result = self.run_measurement(available_through=as_of.date().isoformat() + "T" + time + "+03:00").frame
            self.assertEqual(pd.notna(result.stress_event.iloc[-1]), known)

    def test_holiday_carries_state_not_an_extra_return(self):
        cal = self.calendar.copy()
        cal.loc[649, list(POLICY.mandatory_segments)] = "scheduled_closed"
        rows = self.observations.loc[self.observations.date != self.dates[649]]
        result = self.run_measurement(rows, cal)
        self.assertEqual(len(result.native_frames["fx"]), 649)
        self.assertEqual(result.frame.fx_reference_date.iloc[-1], self.dates[648])
        self.assertEqual(result.frame.stress_event.iloc[-1], 0)

    def test_long_closure_expires_after_seven_calendar_days(self):
        cal = self.calendar.copy()
        cal.loc[640:, list(POLICY.mandatory_segments)] = "scheduled_closed"
        rows = self.observations.loc[self.observations.date < self.dates[640]]
        result = self.run_measurement(rows, cal).frame
        self.assertTrue(pd.isna(result.stress_event.iloc[-1]))

    def test_outage_and_suspension_are_unknown_not_scheduled_holiday(self):
        for state in ("open", "suspended", "unknown"):
            cal = self.calendar.copy()
            cal.loc[649, "equity"] = state
            rows = self.observations.drop(index=self.row("equity", 649))
            self.assertTrue(pd.isna(self.run_measurement(rows, cal).frame.stress_event.iloc[-1]))

    def test_calendar_published_late_cannot_certify_history(self):
        cal = self.calendar.copy()
        cal.loc[649, "known_at"] = "2024-01-01T00:00:00Z"
        result = self.run_measurement(calendar=cal).frame
        self.assertTrue(pd.isna(result.stress_event.iloc[-1]))

    def test_missing_native_slot_breaks_return_window_no_ffill(self):
        rows = self.observations.drop(index=self.row("fx", 640))
        result = self.run_measurement(rows)
        self.assertTrue(pd.isna(result.native_frames["fx"].volatility.iloc[-1]))
        self.assertTrue(pd.isna(result.frame.target.iloc[630]))

    def test_empty_mandatory_source_is_unknown_not_exception_or_zero(self):
        rows = self.observations.loc[self.observations.series_id != POLICY.inputs[0].series_id]
        result = self.run_measurement(rows).frame
        self.assertTrue(result.stress_event.isna().all())

    def test_unknown_publication_stays_null_and_is_not_imputed(self):
        before = self.observations.copy(deep=True)
        self.run_measurement()
        pd.testing.assert_frame_equal(self.observations, before)
        self.assertTrue(self.observations.published_at.isna().all())

    def test_invalid_identity_units_timestamps_values_and_revision_rejected(self):
        for column, value in (("units", "percent_fraction"), ("resource_id", "other"), ("value", -1.), ("value", np.inf), ("value", True), ("received_at", "2020-01-01"), ("published_at", "2025-01-01T00:00:00Z"), ("receipt_sha256", "bad"), ("quality", "stale")):
            rows = self.observations.copy().astype({column: "object"})
            rows.loc[0, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                self.run_measurement(rows)
        with self.assertRaises(ValueError):
            self.run_measurement(pd.concat([self.observations, self.observations.iloc[[0]]]))

    def test_invalid_or_incomplete_calendar_rejected(self):
        for cal in (self.calendar.drop(index=10), self.calendar.iloc[::-1], self.calendar.assign(fx="weekday")):
            with self.assertRaises(ValueError):
                self.run_measurement(calendar=cal)

    def test_live_inputs_and_implicit_snapshot_rejected(self):
        for override in ({"synthetic": False}, {"synthetic": 1}, {"data_snapshot_id": ""}, {"calendar_snapshot_id": ""}, {"available_through": "2023-01-01"}):
            with self.assertRaises(ValueError):
                self.run_measurement(**override)

    def test_prepared_target_and_strict_temporal_mask_keep_measurement_identity(self):
        measured = self.run_measurement()
        prepared = prepared_onset(measured)
        self.assertEqual(prepared.target_definition_id, POLICY.target_definition_id)
        self.assertEqual(prepared.calendar_snapshot_id, measured.calendar_snapshot_id)
        self.assertEqual(prepared.measurement_sha256, MEASUREMENT_SHA256)
        self.assertEqual(measured.measurement_sha256, MEASUREMENT_SHA256)
        rows = training_rows(prepared, cutoff="2021-09-01")
        self.assertFalse(rows.empty)
        self.assertTrue(rows.onset_risk_set.all())
        self.assertTrue((rows.label_end < pd.Timestamp("2021-09-01")).all())

    def test_fold_stub_fit_is_immutable_to_late_revision_and_later_snapshot(self):
        cutoff = pd.Timestamp(self.dates[-1] + pd.Timedelta(days=1, hours=9), tz=POLICY.timezone)
        baseline = self.run_measurement(
            available_through=cutoff.isoformat(),
            data_snapshot_id="synthetic-fold-baseline",
        )
        late_revision = self.observations.iloc[[self.row("fx", 600)]].copy()
        late_revision["value"] = 150.0
        late_revision["receipt_sha256"] = "c" * 64
        late_revision["received_at"] = (
            self.dates[600] + pd.Timedelta(days=1, hours=10)
        ).tz_localize(POLICY.timezone).isoformat()
        revised_rows = pd.concat([self.observations, late_revision], ignore_index=True)
        revised = self.run_measurement(
            revised_rows,
            available_through=cutoff.isoformat(),
            data_snapshot_id="synthetic-fold-with-late-revision",
        )

        estimators = []
        batches = []
        for measured in (baseline, revised):
            prepared = prepared_onset(measured)
            features = pd.DataFrame(
                {"synthetic_feature": np.arange(len(prepared.frame), dtype=float)},
                index=prepared.frame.index,
            )
            snapshot = FeatureSnapshot(
                snapshot_id="features-" + measured.data_snapshot_id,
                schema_id="synthetic-feature-schema.1",
                available_through=cutoff,
                frame=features,
            )
            batch = fold_training_batch(prepared, snapshot, cutoff=cutoff)
            estimator = RecordingEstimator().fit(batch.features, batch.target)
            estimators.append(estimator)
            batches.append(batch)

        self.assertTrue(estimators[0].fit_index.equals(estimators[1].fit_index))
        pd.testing.assert_series_equal(estimators[0].fit_target, estimators[1].fit_target)
        self.assertEqual(batches[0].task_id, "ru_market_stress_onset_v1")
        self.assertEqual(batches[0].target_definition_id, POLICY.target_definition_id)
        self.assertEqual(batches[0].horizon_days, 30)
        self.assertTrue((batches[0].origins + pd.Timedelta(days=30) < cutoff.tz_localize(None).normalize()).all())

        later = self.run_measurement(
            revised_rows,
            available_through="2023-01-01T12:00:00+03:00",
            data_snapshot_id="synthetic-later-snapshot",
        )
        later_prepared = prepared_onset(later)
        later_features = FeatureSnapshot(
            snapshot_id="features-later",
            schema_id="synthetic-feature-schema.1",
            available_through="2023-01-01T12:00:00+03:00",
            frame=pd.DataFrame(
                {"synthetic_feature": np.arange(len(later_prepared.frame), dtype=float)},
                index=later_prepared.frame.index,
            ),
        )
        with self.assertRaisesRegex(ValueError, "later snapshots are forbidden"):
            fold_training_batch(later_prepared, later_features, cutoff=cutoff)


if __name__ == "__main__":
    unittest.main()
