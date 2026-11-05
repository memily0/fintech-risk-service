"""Synthetic examples only: no real provider responses or model evaluation."""

from copy import deepcopy
import csv
import json
import re
import unittest

from jsonschema import Draft202012Validator, ValidationError

from v1_data_contract import DIRECTORY, assert_candidate_usage_blocked, known_and_effective_by, load_contract, normalize_cpi_yoy, select_curve_points, validate_observation


def example(column="usd_rub"):
    series = next(s for s in load_contract()["raw_series"] if s["legacy_column"] == column)
    record = {
        "schema_version": "candidate.1",
        "series_id": series["series_id"],
        "definition_version": "candidate.1",
        "resource_id": series["resource_id"],
        "units": series["units"],
        "value": 100.0,
        "quality": "observed",
        "reference_start": "2026-11-05",
        "reference_end": "2026-11-05",
        "effective_date": "2026-11-05",
        "published_at": "2026-11-05T08:00:00+03:00",
        "publication_status": "known",
        "received_at": "2026-11-05T09:00:00+03:00",
        "source_timezone": series["timezone"],
        "snapshot_id": "synthetic-contract-test-not-market-data",
        "receipt_sha256": "0" * 64,
        "dimensions": deepcopy(series["dimensions"]),
        "is_synthetic": True,
    }
    if column == "inflation":
        record.update(reference_start="2026-09-01", reference_end="2026-09-30", effective_date=None)
    return record


class DataContractTests(unittest.TestCase):
    def rejected(self, record):
        with self.assertRaises((ValueError, ValidationError)):
            validate_observation(record)

    def test_schema_is_valid_draft_2020_12(self):
        schema = json.loads((DIRECTORY / "observation.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        self.assertNotIn("$ref", json.dumps(schema))

    def test_all_legacy_columns_have_distinct_candidate_definitions(self):
        contract = load_contract()
        columns = [s["legacy_column"] for s in [*contract["raw_series"], *contract["derived_series"]]]
        with (DIRECTORY.parent / "v1_source_audit/series_catalog.csv").open(newline="", encoding="utf-8") as stream:
            self.assertEqual(columns, [r["column"] for r in csv.DictReader(stream)])
        self.assertEqual(len({s["series_id"] for s in contract["raw_series"]}), 13)

    def test_valid_synthetic_observation(self):
        self.assertEqual(validate_observation(example())["legacy_column"], "usd_rub")

    def test_naive_or_invalid_timestamps_rejected(self):
        for stamp in ("2026-11-05T09:00:00", "yesterday", "2026-13-05T09:00:00Z"):
            with self.subTest(stamp=stamp):
                record = example()
                record["received_at"] = stamp
                self.rejected(record)

    def test_wrong_units_resource_definition_and_unknown_series_rejected(self):
        for key, value in (("units", "USD_per_RUB"), ("resource_id", "spot:USDRUB"), ("definition_version", "legacy"), ("series_id", "unknown")):
            with self.subTest(key=key):
                record = example()
                record[key] = value
                self.rejected(record)

    def test_reversed_invalid_period_and_bad_provenance_shape_rejected(self):
        for key, value in (("reference_start", "2026-11-06"), ("reference_end", "2026-02-30"), ("receipt_sha256", "0" * 64 + "\n"), ("source_timezone", "UTC")):
            with self.subTest(key=key):
                record = example()
                record[key] = value
                self.rejected(record)

    def test_boolean_and_nonfinite_values_rejected(self):
        for value in (True, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                record = example()
                record["value"] = value
                self.rejected(record)

    def test_missing_is_not_zero_or_observed(self):
        record = example()
        record.update(value=None, quality="missing")
        validate_observation(record)
        self.assertFalse(known_and_effective_by(record, "2026-11-05T10:00:00+03:00"))
        record["value"] = 0
        self.rejected(record)

    def test_unknown_publication_is_nullable_not_invented(self):
        record = example()
        record.update(published_at=None, publication_status="unknown")
        validate_observation(record)
        self.assertFalse(known_and_effective_by(record, "2026-11-05T08:30:00+03:00"))
        self.assertTrue(known_and_effective_by(record, "2026-11-05T09:00:00+03:00"))
        record["published_at"] = "2026-11-05T08:00:00+03:00"
        self.rejected(record)

    def test_publication_cannot_follow_actual_receipt(self):
        record = example()
        record["published_at"] = "2026-11-05T12:00:00+03:00"
        self.rejected(record)

    def test_receipt_is_knowledge_boundary_even_with_old_publication(self):
        record = example("inflation")
        record["published_at"] = "2026-10-09T19:00:00+03:00"
        self.assertFalse(known_and_effective_by(record, "2026-10-10T09:00:00+03:00"))
        self.assertTrue(known_and_effective_by(record, "2026-11-05T09:00:00+03:00"))

    def test_effective_date_is_required_and_future_not_active(self):
        record = example("key_rate")
        record["effective_date"] = None
        self.rejected(record)
        record["effective_date"] = "2026-11-06"
        validate_observation(record)
        self.assertFalse(known_and_effective_by(record, "2026-11-05T12:00:00+03:00"))

    def test_timezone_equivalent_origin_and_effective_local_date(self):
        self.assertTrue(known_and_effective_by(example(), "2026-11-05T06:00:00Z"))
        record = example()
        record.update(received_at="2026-11-04T20:00:00Z", published_at="2026-11-04T19:00:00Z")
        self.assertTrue(known_and_effective_by(record, "2026-11-04T21:01:00Z"))
        self.assertFalse(known_and_effective_by(record, "2026-11-04T20:59:00Z"))

    def test_us_close_cannot_be_used_at_moscow_morning_origin(self):
        record = example("sp500")
        record.update(reference_start="2026-11-04", reference_end="2026-11-04", effective_date=None,
                      published_at="2026-11-04T16:00:00-05:00", received_at="2026-11-05T00:05:00+03:00")
        self.assertFalse(known_and_effective_by(record, "2026-11-04T09:00:00+03:00"))

    def test_naive_origin_rejected(self):
        with self.assertRaises(ValueError):
            known_and_effective_by(example(), "2026-11-05T10:00:00")

    def test_old_known_record_is_not_a_freshness_verdict(self):
        self.assertTrue(known_and_effective_by(example(), "2026-12-05T10:00:00+03:00"))
        self.assertTrue(load_contract()["availability_policy"]["market_calendar_and_staleness_checks_required_separately"])

    def test_cpi_wrong_base_region_or_row_position_rejected(self):
        for key, value in (("comparison", "previous_month"), ("territory", "regional"), ("frequency", "weekly")):
            record = example("inflation")
            record["dimensions"][key] = value
            self.rejected(record)
        record = example("inflation")
        record["dimensions"] = {"occurrence": 1}
        self.rejected(record)

    def test_cpi_complete_month_and_no_fake_effective_date(self):
        for key, value in (("reference_start", "2026-09-02"), ("reference_end", "2026-09-29"), ("effective_date", "2026-10-01")):
            record = example("inflation")
            record[key] = value
            self.rejected(record)

    def test_cpi_normalization_is_not_index_level(self):
        dims = example("inflation")["dimensions"]
        self.assertEqual(normalize_cpi_yoy(105.0, dims), 5.0)
        self.assertEqual(normalize_cpi_yoy(99.0, dims), -1.0)
        for invalid in (True, 0, float("nan")):
            with self.assertRaises(ValueError):
                normalize_cpi_yoy(invalid, dims)
        with self.assertRaises(ValueError):
            normalize_cpi_yoy(105, {**dims, "comparison": "YTD"})

    def test_key_rate_not_refinancing_or_pre_definition_history(self):
        record = example("key_rate")
        record["reference_start"] = record["reference_end"] = "2008-01-01"
        self.rejected(record)
        record = example("key_rate")
        record["dimensions"]["rate_type"] = "refinancing_rate"
        self.rejected(record)

    def test_curve_selection_uses_headers_not_cell_position(self):
        expected = {"ofz_1y": 11, "ofz_2y": 12, "ofz_5y": 15, "ofz_10y": 20}
        self.assertEqual(select_curve_points(["10", "0,25", "2", "1", "5"], [20, 3, 12, 11, 15]), expected)
        self.assertEqual(select_curve_points(["5", "1", "10", "2"], [15, 11, 20, 12]), expected)

    def test_curve_missing_duplicate_or_bad_headers_rejected(self):
        for headers, values in (([1, 2, 5], [1, 2, 5]), ([1, 1, 2, 5, 10], [1, 1, 2, 5, 10]), ([1, 2, 5, "ten"], [1, 2, 5, 10]), ([1, 2, 5, 10], [1, 2]), ([1, 2, 5, 10], [1, 2, None, 10])):
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                select_curve_points(headers, values)

    def test_dimension_types_are_not_coerced(self):
        record = example("ofz_1y")
        record["dimensions"]["maturity_years"] = True
        self.rejected(record)

    def test_client_cannot_inject_rights_flags(self):
        record = example()
        record["rights_approved"] = True
        self.rejected(record)

    def test_candidate_usage_remains_blocked_in_all_modes(self):
        for mode in load_contract()["usage_modes"]:
            with self.subTest(mode=mode), self.assertRaises(PermissionError):
                assert_candidate_usage_blocked(example(), mode)

    def test_unresolved_cpi_binding_and_no_silent_weight_reuse(self):
        contract = load_contract()
        cpi = next(s for s in contract["raw_series"] if s["legacy_column"] == "inflation")
        self.assertFalse(cpi["dimension_codes_verified"])
        self.assertIsNone(cpi["download_resource_url"])
        self.assertFalse(contract["production_admission"])
        self.assertFalse(contract["compatibility"]["legacy_weights_reusable_without_new_evaluation"])
        self.assertFalse(contract["compatibility"]["incomplete_stress_components_may_be_silently_dropped"])
        self.assertFalse(contract["dedicated_Kazakhstan_scope"])

    def test_handoff_and_document_links_preserve_open_status(self):
        status = json.loads((DIRECTORY / "step_status.json").read_text())
        self.assertFalse(status["substep_fully_closed"])
        self.assertFalse(status["CPI_exact_resource_and_dimension_codes_verified"])
        self.assertFalse(status["source_usage_admission_complete"])
        with (DIRECTORY / "finding_handoff.csv").open(newline="", encoding="utf-8") as stream:
            handoff = list(csv.DictReader(stream))
        self.assertEqual({r["finding_id"] for r in handoff}, {f"DS{i:02d}" for i in range(1, 13)})
        self.assertTrue(all(r["runtime_resolution"] == "open" for r in handoff))
        for path in (DIRECTORY / "README.md", DIRECTORY / "rights_questions.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if not target.startswith(("http://", "https://", "#")):
                    self.assertTrue((path.parent / target).is_file(), target)


if __name__ == "__main__":
    unittest.main()
