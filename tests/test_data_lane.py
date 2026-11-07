import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from arcshift_data import (
    JsonObservationStore,
    RateLimitError,
    SchedulerLock,
    load_source_registry,
    parse_cboe_vix_csv,
    parse_cbr_currency_xml,
    parse_cbr_curve_html,
    parse_cbr_key_rate_xml,
    parse_moex_imoex_json,
    parse_rosstat_cpi_json,
    receipt_freshness_state,
    run_with_bounded_retry,
)


RECEIVED_AT = "2026-11-05T09:00:00+03:00"
SNAPSHOT_ID = "synthetic-data-lane-test"

USD_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ValCurs ID="R01235">
  <Record Date="05.11.2026" Id="R01235">
    <Nominal>10</Nominal>
    <Value>800,00</Value>
    <VunitRate>80,00</VunitRate>
  </Record>
</ValCurs>
"""

CURVE_HTML = """
<table>
  <tr><th>Дата</th><th>10</th><th>0,25</th><th>2</th><th>1</th><th>5</th></tr>
  <tr><td>05.11.2026</td><td>16,4</td><td>13,1</td><td>15,1</td><td>14,2</td><td>16,0</td></tr>
</table>
""".encode("utf-8")

SYNTHETIC_CPI_CODES = {
    "territory": "SYNTHETIC_RUSSIA",
    "coverage": "SYNTHETIC_ALL_ITEMS",
    "comparison": "SYNTHETIC_SAME_MONTH_LAST_YEAR",
    "frequency": "SYNTHETIC_MONTHLY",
}

KEY_RATE_XML = b"""<KeyRateResult><KeyRate>
  <KR><DT>2026-11-05T00:00:00+03:00</DT><Rate>14.0</Rate></KR>
</KeyRate></KeyRateResult>"""

IMOEX_JSON = json.dumps(
    {"history": {"columns": ["TRADEDATE", "CLOSE", "SECID"], "data": [["2026-11-05", 2540.5, "IMOEX"]]}}
).encode()

VIX_CSV = b"DATE,OPEN,HIGH,LOW,CLOSE\n11/04/2026,18.1,19.3,17.9,18.7\n"


def make_cpi_payload(extra_rows=None):
    rows = [
        {
            "period": "2026-09",
            "dimension_codes": {
                **SYNTHETIC_CPI_CODES,
                "comparison": "SYNTHETIC_PREVIOUS_MONTH",
            },
            "index_percent": 100.4,
        },
        {
            "period": "2026-09",
            "dimension_codes": SYNTHETIC_CPI_CODES,
            "index_percent": 105.5,
        },
    ]
    rows.extend(extra_rows or [])
    return json.dumps(
        {"indicator_id": "11521100300010200001", "rows": rows}
    ).encode("utf-8")


class SourceRegistryTests(unittest.TestCase):
    def test_registry_is_complete_and_all_real_requests_are_blocked(self):
        registry = load_source_registry()
        self.assertEqual(len(registry["sources"]), 9)
        for source in registry["sources"]:
            self.assertFalse(source["production_admitted"])
            self.assertTrue(all(value == "pending" for value in source["rights"].values()))
            self.assertEqual(
                source["request_budget"],
                {"technical_probe": 0, "backfill": 0, "incremental_per_run": 0},
            )

    def test_registry_covers_every_candidate_raw_resource(self):
        registry = load_source_registry()
        registered_resource_ids = {
            resource_id
            for source in registry["sources"]
            for resource_id in source["series"]
        }
        contract_path = (
            Path(__file__).resolve().parents[1]
            / "product_build/arcshift_v1/research/08_product_handoff/v1_data_contract/candidate_contract.json"
        )
        candidate_contract = json.loads(contract_path.read_text(encoding="utf-8"))
        candidate_resource_ids = {
            source["resource_id"] for source in candidate_contract["raw_series"]
        }
        self.assertEqual(registered_resource_ids, candidate_resource_ids)

    def test_registry_has_exact_time_and_calendar_bindings_for_priority_sources(self):
        registry = load_source_registry()
        priority = {"cbr_key_rate", "rosstat_cpi_yoy", "moex_imoex", "cboe_vix"}
        bindings = {
            source["source_id"]: source.get("exact_binding")
            for source in registry["sources"]
            if source["source_id"] in priority
        }
        self.assertEqual(set(bindings), priority)
        for binding in bindings.values():
            self.assertIn("calendar_id", binding)
            self.assertTrue(
                "receipt" in binding["availability_rule"]
                or "received_at" in binding["availability_rule"]
            )


class ParserTests(unittest.TestCase):
    def test_currency_nominal_is_normalized_to_one_unit(self):
        observations = parse_cbr_currency_xml(USD_XML, "R01235", RECEIVED_AT, SNAPSHOT_ID, True)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["value"], 80.0)
        self.assertEqual(observations[0]["units"], "RUB_per_USD")
        self.assertEqual(observations[0]["effective_date"], "2026-11-05")

    def test_currency_rejects_bad_nominal_wrong_id_conflict_and_broken_xml(self):
        bad_payloads = [
            USD_XML.replace(b"<Nominal>10</Nominal>", b"<Nominal>0</Nominal>"),
            USD_XML.replace(b"R01235", b"R01239"),
            USD_XML.replace(b"<VunitRate>80,00</VunitRate>", b"<VunitRate>81,00</VunitRate>"),
            b"<ValCurs>",
        ]
        for bad_payload in bad_payloads:
            with self.subTest(payload=bad_payload), self.assertRaises(ValueError):
                parse_cbr_currency_xml(bad_payload, "R01235", RECEIVED_AT, SNAPSHOT_ID, True)

    def test_currency_rejects_bad_date_and_naive_receipt_time(self):
        bad_date_payload = USD_XML.replace(b"05.11.2026", b"32.11.2026")
        with self.assertRaises(ValueError):
            parse_cbr_currency_xml(bad_date_payload, "R01235", RECEIVED_AT, SNAPSHOT_ID, True)
        with self.assertRaises(ValueError):
            parse_cbr_currency_xml(USD_XML, "R01235", "2026-11-05T09:00:00", SNAPSHOT_ID, True)

    def test_curve_uses_tenor_headers_instead_of_column_positions(self):
        observations = parse_cbr_curve_html(CURVE_HTML, RECEIVED_AT, SNAPSHOT_ID, True)
        values_by_maturity = {
            item["dimensions"]["maturity_years"]: item["value"]
            for item in observations
        }
        self.assertEqual(values_by_maturity, {1: 14.2, 2: 15.1, 5: 16.0, 10: 16.4})

    def test_curve_rejects_missing_duplicate_and_broken_schema(self):
        missing_tenor = CURVE_HTML.replace(b"<th>10</th>", b"<th>15</th>")
        duplicate_tenor = CURVE_HTML.replace(b"<th>0,25</th>", b"<th>1</th>")
        broken_row = CURVE_HTML.replace(b"<td>16,0</td>", b"")
        for bad_payload in (missing_tenor, duplicate_tenor, broken_row, b"<p>no table</p>"):
            with self.subTest(payload=bad_payload), self.assertRaises(ValueError):
                parse_cbr_curve_html(bad_payload, RECEIVED_AT, SNAPSHOT_ID, True)

    def test_cpi_selects_dimensions_not_row_position(self):
        observations = parse_rosstat_cpi_json(
            make_cpi_payload(), SYNTHETIC_CPI_CODES, RECEIVED_AT, SNAPSHOT_ID, True
        )
        self.assertEqual(observations[0]["value"], 5.5)
        self.assertEqual(observations[0]["reference_start"], "2026-09-01")
        self.assertEqual(observations[0]["reference_end"], "2026-09-30")

    def test_cpi_rejects_missing_wrong_or_ambiguous_dimensions(self):
        incomplete_codes = dict(SYNTHETIC_CPI_CODES)
        incomplete_codes.pop("comparison")
        with self.assertRaises(ValueError):
            parse_rosstat_cpi_json(make_cpi_payload(), incomplete_codes, RECEIVED_AT, SNAPSHOT_ID, True)

        wrong_codes = {**SYNTHETIC_CPI_CODES, "territory": "SYNTHETIC_REGION"}
        with self.assertRaises(ValueError):
            parse_rosstat_cpi_json(make_cpi_payload(), wrong_codes, RECEIVED_AT, SNAPSHOT_ID, True)

        duplicate_row = {
            "period": "2026-09",
            "dimension_codes": SYNTHETIC_CPI_CODES,
            "index_percent": 105.6,
        }
        with self.assertRaises(ValueError):
            parse_rosstat_cpi_json(
                make_cpi_payload([duplicate_row]),
                SYNTHETIC_CPI_CODES,
                RECEIVED_AT,
                SNAPSHOT_ID,
                True,
            )

    def test_cpi_rejects_wrong_indicator_bad_period_and_broken_json(self):
        wrong_indicator = make_cpi_payload().replace(
            b"11521100300010200001", b"wrong-indicator"
        )
        bad_period = make_cpi_payload().replace(b"2026-09", b"2026-13")
        for bad_payload in (wrong_indicator, bad_period, b"not-json"):
            with self.subTest(payload=bad_payload), self.assertRaises(ValueError):
                parse_rosstat_cpi_json(
                    bad_payload, SYNTHETIC_CPI_CODES, RECEIVED_AT, SNAPSHOT_ID, True
                )

    def test_genuine_key_rate_has_effective_day_and_no_refinancing_fallback(self):
        row = parse_cbr_key_rate_xml(KEY_RATE_XML, RECEIVED_AT, SNAPSHOT_ID, True)[0]
        self.assertEqual(row["series_id"], "ru.policy.cbr.key_rate")
        self.assertEqual(row["resource_id"], "cbr:DailyInfo:KeyRate")
        self.assertEqual(row["effective_date"], "2026-11-05")
        self.assertEqual(row["value"], 14.0)
        self.assertIsNone(row["published_at"])
        with self.assertRaises(ValueError):
            parse_cbr_key_rate_xml(
                b"<Root><Row><DT>2013-09-16</DT><Rate>5.5</Rate></Row></Root>",
                RECEIVED_AT,
                SNAPSHOT_ID,
                True,
            )

    def test_imoex_and_vix_use_named_official_close_fields(self):
        imoex = parse_moex_imoex_json(IMOEX_JSON, RECEIVED_AT, SNAPSHOT_ID, True)[0]
        vix = parse_cboe_vix_csv(VIX_CSV, RECEIVED_AT, SNAPSHOT_ID, True)[0]
        self.assertEqual(imoex["series_id"], "ru.equity.imoex.close")
        self.assertEqual(imoex["value"], 2540.5)
        self.assertEqual(imoex["source_timezone"], "Europe/Moscow")
        self.assertEqual(vix["series_id"], "global.volatility.cboe.vix.close")
        self.assertEqual(vix["value"], 18.7)
        self.assertEqual(vix["source_timezone"], "America/New_York")

    def test_imoex_and_vix_reject_wrong_instrument_or_schema(self):
        wrong_imoex = IMOEX_JSON.replace(b"IMOEX", b"IMOEX2")
        bad_vix = b"DATE,CLOSE\n11/04/2026,18.7\n"
        with self.assertRaises(ValueError):
            parse_moex_imoex_json(wrong_imoex, RECEIVED_AT, SNAPSHOT_ID, True)
        with self.assertRaises(ValueError):
            parse_cboe_vix_csv(bad_vix, RECEIVED_AT, SNAPSHOT_ID, True)


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "observations.json"
        self.store = JsonObservationStore(self.state_path)
        self.observation = parse_cbr_currency_xml(
            USD_XML, "R01235", RECEIVED_AT, SNAPSHOT_ID, True
        )[0]

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_publish_is_atomic_idempotent_and_keeps_revisions(self):
        first_result = self.store.publish([self.observation], "2026-11-05T09:01:00+03:00")
        duplicate_result = self.store.publish([self.observation], "2026-11-05T09:02:00+03:00")

        revised_observation = copy.deepcopy(self.observation)
        revised_observation["value"] = 80.5
        revised_observation["received_at"] = "2026-11-05T09:03:00+03:00"
        revised_observation["receipt_sha256"] = "1" * 64
        revision_result = self.store.publish([revised_observation], "2026-11-05T09:04:00+03:00")

        state = self.store.read()
        self.assertEqual(first_result["added_count"], 1)
        self.assertEqual(duplicate_result["duplicate_count"], 1)
        self.assertEqual(first_result["snapshot_id"], duplicate_result["snapshot_id"])
        self.assertEqual(revision_result["added_count"], 1)
        self.assertEqual(len(state["revisions"]), 2)
        self.assertEqual(list(state["latest"].values())[0]["observation"]["value"], 80.5)
        self.assertFalse(list(self.state_path.parent.glob("*.tmp")))

    def test_same_receipt_cannot_describe_a_different_value(self):
        self.store.publish([self.observation], "2026-11-05T09:01:00+03:00")
        conflicting_observation = copy.deepcopy(self.observation)
        conflicting_observation["value"] = 999.0
        with self.assertRaises(ValueError):
            self.store.publish([conflicting_observation], "2026-11-05T09:02:00+03:00")

    def test_bad_receipt_hash_and_empty_publish_are_rejected(self):
        bad_hash_observation = copy.deepcopy(self.observation)
        bad_hash_observation["receipt_sha256"] = "not-a-hash"
        with self.assertRaises(ValueError):
            self.store.publish([bad_hash_observation], "2026-11-05T09:01:00+03:00")
        with self.assertRaises(ValueError):
            self.store.publish([], "2026-11-05T09:01:00+03:00")

    def test_out_of_order_revision_is_saved_but_does_not_replace_latest(self):
        self.store.publish([self.observation], "2026-11-05T09:01:00+03:00")
        older_observation = copy.deepcopy(self.observation)
        older_observation["value"] = 79.0
        older_observation["received_at"] = "2026-11-05T08:00:00+03:00"
        older_observation["receipt_sha256"] = "2" * 64
        self.store.publish([older_observation], "2026-11-05T09:02:00+03:00")

        state = self.store.read()
        self.assertEqual(len(state["revisions"]), 2)
        self.assertEqual(list(state["latest"].values())[0]["observation"]["value"], 80.0)

    def test_real_observation_is_blocked_before_source_admission(self):
        real_observation = copy.deepcopy(self.observation)
        real_observation["is_synthetic"] = False
        with self.assertRaises(PermissionError):
            self.store.publish([real_observation], "2026-11-05T09:01:00+03:00")

    def test_only_one_scheduler_can_hold_the_lock(self):
        lock_path = Path(self.temporary_directory.name) / "scheduler.lock"
        with SchedulerLock(lock_path):
            with self.assertRaises(RuntimeError):
                with SchedulerLock(lock_path):
                    pass
        self.assertFalse(lock_path.exists())

    def test_scheduler_recovers_lock_left_by_crashed_process(self):
        lock_path = Path(self.temporary_directory.name) / "crashed-worker.lock"
        code = (
            "import os; from arcshift_data import SchedulerLock; "
            f"lock=SchedulerLock({str(lock_path)!r}); lock.__enter__(); os._exit(23)"
        )
        result = subprocess.run([sys.executable, "-c", code], env=dict(os.environ), timeout=10)
        self.assertEqual(result.returncode, 23)
        self.assertTrue(lock_path.exists())
        with SchedulerLock(lock_path):
            self.assertTrue(lock_path.exists())
        self.assertFalse(lock_path.exists())

    def test_freshness_states_are_explicit(self):
        self.assertEqual(
            receipt_freshness_state(self.observation, "2026-11-05T09:05:00+03:00", 600, "open"),
            "fresh",
        )
        self.assertEqual(
            receipt_freshness_state(self.observation, "2026-11-05T10:00:00+03:00", 600, "open"),
            "stale",
        )
        self.assertEqual(
            receipt_freshness_state(self.observation, RECEIVED_AT, 600, "closed"),
            "market_closed",
        )
        self.assertEqual(
            receipt_freshness_state(self.observation, RECEIVED_AT, 600, "holiday"),
            "calendar_holiday",
        )
        self.assertEqual(receipt_freshness_state(None, RECEIVED_AT, 600, "open"), "unavailable")


class RetryTests(unittest.TestCase):
    def test_rate_limit_is_retried_with_a_bound(self):
        attempts = []
        waits = []

        def sometimes_rate_limited():
            attempts.append("attempt")
            if len(attempts) < 3:
                raise RateLimitError("synthetic 429")
            return "ok"

        result = run_with_bounded_retry(
            sometimes_rate_limited,
            maximum_attempts=3,
            wait_seconds=(1, 2),
            sleep_function=waits.append,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(waits, [1, 2])

    def test_timeout_stops_after_the_last_attempt(self):
        attempts = []

        def always_times_out():
            attempts.append("attempt")
            raise TimeoutError("synthetic timeout")

        with self.assertRaises(TimeoutError):
            run_with_bounded_retry(always_times_out, maximum_attempts=2, wait_seconds=(0,))
        self.assertEqual(len(attempts), 2)

    def test_retry_after_is_honored_but_capped(self):
        waits = []
        attempts = []

        def limited_once():
            attempts.append(1)
            if len(attempts) == 1:
                raise RateLimitError(retry_after_seconds=120)
            return "ok"

        result = run_with_bounded_retry(
            limited_once,
            maximum_attempts=2,
            wait_seconds=(1,),
            maximum_wait_seconds=5,
            sleep_function=waits.append,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(waits, [5])

    def test_non_retryable_error_is_not_retried(self):
        attempts = []

        def broken_schema():
            attempts.append("attempt")
            raise ValueError("broken schema")

        with self.assertRaises(ValueError):
            run_with_bounded_retry(broken_schema)
        self.assertEqual(len(attempts), 1)


if __name__ == "__main__":
    unittest.main()
