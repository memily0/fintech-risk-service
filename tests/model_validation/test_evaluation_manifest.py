"""Candidate protocol identity tests only; no estimator or artifact is created."""

import unittest

from arcshift_v1.stress_definition import MEASUREMENT_SHA256, STRESS_DEFINITION
from arcshift_v1.task_definition import TASK_DEFINITION
from models.validation.evaluation import MANIFEST_CANDIDATE


class EvaluationManifestTests(unittest.TestCase):
    def test_manifest_reuses_frozen_task_and_measurement_identity(self):
        self.assertEqual(MANIFEST_CANDIDATE.task_id, TASK_DEFINITION.task_id)
        self.assertEqual(MANIFEST_CANDIDATE.target_definition_id, "ru_domestic_stress_onset.1")
        self.assertEqual(MANIFEST_CANDIDATE.measurement_id, "ru-domestic-market-stress.1")
        self.assertEqual(MANIFEST_CANDIDATE.measurement_sha256, MEASUREMENT_SHA256)
        self.assertEqual(MANIFEST_CANDIDATE.measurement_sha256, TASK_DEFINITION.measurement_sha256)
        self.assertEqual(MANIFEST_CANDIDATE.measurement_id, STRESS_DEFINITION.measurement_id)

    def test_manifest_has_one_horizon_and_finite_comparison(self):
        self.assertEqual(MANIFEST_CANDIDATE.horizon_calendar_days, 30)
        self.assertEqual(MANIFEST_CANDIDATE.baseline, "training_prevalence_constant")
        self.assertEqual(MANIFEST_CANDIDATE.comparator, "l2_logistic_regression_c_1")
        self.assertEqual(MANIFEST_CANDIDATE.logistic_c, 1.0)
        self.assertEqual(MANIFEST_CANDIDATE.logistic_class_weight, "none")
        self.assertEqual(
            MANIFEST_CANDIDATE.preprocessing,
            ("train_median_imputation", "train_standard_scaling"),
        )
        self.assertEqual(MANIFEST_CANDIDATE.random_seed, 42)
        self.assertEqual(MANIFEST_CANDIDATE.outer_fold_count, 4)
        self.assertEqual(MANIFEST_CANDIDATE.inner_fold_count, 3)
        self.assertEqual(MANIFEST_CANDIDATE.max_estimator_fits_per_outer_fold, 5)
        self.assertTrue(MANIFEST_CANDIDATE.matched_origins_required)

    def test_manifest_is_proposed_and_cannot_authorize_m04(self):
        self.assertEqual(MANIFEST_CANDIDATE.status, "proposed_not_authorized")
        self.assertEqual(MANIFEST_CANDIDATE.exact_outer_cutoffs, ())
        self.assertEqual(MANIFEST_CANDIDATE.feature_schema_status, "pending_admitted_snapshot")
        self.assertEqual(MANIFEST_CANDIDATE.warning_threshold_status, "pending_product_decision")
        self.assertEqual(MANIFEST_CANDIDATE.numeric_acceptance_status, "pending_product_decision")
        self.assertFalse(MANIFEST_CANDIDATE.m04_authorized)


if __name__ == "__main__":
    unittest.main()
