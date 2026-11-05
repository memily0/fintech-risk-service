"""Portable handoff checks. No network, provider data, model imports or fits."""

import csv
import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "research/08_product_handoff"


def table(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class BundleTests(unittest.TestCase):
    def test_inventory_hashes_and_no_unlisted_payload(self):
        rows = table(ROOT / "PACKAGE_CONTENTS.csv")
        expected = {r["path"] for r in rows}
        actual = {
            str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
            if p.is_file() and not any(part in {".venv", "__pycache__", ".git"} for part in p.relative_to(ROOT).parts)
        } - {"PACKAGE_CONTENTS.csv"}
        self.assertEqual(actual, expected)
        for row in rows:
            path = ROOT / row["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"], row["path"])
            self.assertEqual(path.stat().st_size, int(row["bytes"]))

    def test_text_only_and_no_obvious_secrets_or_private_paths(self):
        banned = {".pdf", ".docx", ".joblib", ".pkl", ".pickle", ".zip", ".xls", ".xlsx", ".mov", ".wav", ".mp3", ".mp4", ".pem", ".key", ".sqlite", ".db"}
        patterns = [
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            r"\bgh[pousr]_[A-Za-z0-9]{30,}\b",
            r"\bgithub_pat_[A-Za-z0-9_]{30,}\b",
            r"\bAKIA[A-Z0-9]{16}\b",
            r"/(?:Users|home)/[A-Za-z0-9_.-]+/",
        ]
        for row in table(ROOT / "PACKAGE_CONTENTS.csv"):
            path = ROOT / row["path"]
            self.assertNotIn(path.suffix.lower(), banned, row["path"])
            self.assertFalse(path.name.startswith(".env"))
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                self.assertIsNone(re.search(pattern, text), row["path"])

    def test_local_markdown_links_exist(self):
        for row in table(ROOT / "PACKAGE_CONTENTS.csv"):
            path = ROOT / row["path"]
            if path.suffix != ".md":
                continue
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if target.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                target = unquote(target.split("#", 1)[0])
                self.assertTrue((path.parent / target).is_file(), f"{row['path']}: {target}")

    def test_work_packages_dependencies_and_coverage(self):
        rows = table(ROOT / "work_packages.csv")
        remaining = {r["id"]: set(r["depends_on"].split()) - {"none"} for r in rows}
        self.assertEqual(len(rows), 28)
        self.assertEqual(len(remaining), 28)
        ids = set(remaining)
        self.assertTrue(all(deps <= ids for deps in remaining.values()))
        done = set()
        while remaining:
            ready = {key for key, deps in remaining.items() if deps <= done}
            self.assertTrue(ready, "Cyclic dependency")
            done |= ready
            remaining = {key: deps for key, deps in remaining.items() if key not in ready}
        self.assertEqual({stage for r in rows for stage in r["original_stage"].split()}, {str(i) for i in range(12)})
        self.assertTrue(all(r["status"] == "proposed_not_started" for r in rows))

    def test_scope_and_research_boundaries(self):
        contract = json.loads((HANDOFF / "v1_data_contract/candidate_contract.json").read_text())
        self.assertEqual(contract["primary_country"], "RU")
        self.assertFalse(contract["dedicated_Kazakhstan_scope"])
        self.assertEqual(contract["public_access"], "public_self_registration")
        self.assertFalse(contract["production_admission"])
        self.assertFalse(contract["compatibility"]["legacy_weights_reusable_without_new_evaluation"])
        gates = table(HANDOFF / "arcshift_v1_release_checklist.csv")
        self.assertEqual(len(gates), 22)
        self.assertTrue(all(r["status"] == "pending" for r in gates))

    def test_acceptance_and_source_coverage(self):
        self.assertEqual(len(table(HANDOFF / "v1_product_specification/acceptance_scenarios.csv")), 40)
        rows = table(HANDOFF / "v1_source_audit/series_catalog.csv")
        self.assertEqual(sum(r["kind"] == "raw" for r in rows), 13)
        self.assertEqual(sum(r["kind"] == "derived" for r in rows), 6)
        self.assertTrue(all(r["production_admission"] == "pending" for r in rows))

    def test_fixtures_are_never_live_claims(self):
        ui = json.loads((ROOT / "fixtures/ui_scenarios.json").read_text())
        self.assertTrue(ui["synthetic"])
        self.assertTrue(all(s["synthetic"] for s in ui["scenarios"]))
        self.assertTrue(all(s["signal"] is None or s["signal"]["validity_status"] == "historical_demo" for s in ui["scenarios"]))
        obs = json.loads((ROOT / "fixtures/observation.json").read_text())
        self.assertTrue(obs["is_synthetic"])

    def test_publication_is_selected_not_entire_private_archive(self):
        manifest = json.loads((ROOT / "publication_manifest.json").read_text())
        self.assertEqual(manifest["repository_visibility"], "PUBLIC")
        self.assertTrue(manifest["selected_package_publication_authorized_by_latest_user_request"])
        self.assertFalse(manifest["entire_private_research_archive_published"])
        self.assertFalse(manifest["raw_interviews_or_JST_data_published"])
        self.assertFalse(manifest["product_release_approved"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
