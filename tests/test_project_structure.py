from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectStructureTest(unittest.TestCase):
    def test_required_directories_exist(self) -> None:
        required_directories = (
            "app/dashboard",
            "app/services",
            "app/components",
            "configs",
            "data/raw",
            "data/processed",
            "data/external",
            "docs",
            "models/training",
            "models/inference",
            "models/artifacts",
            "research/p1_model_comparison",
            "research/p2_feature_research",
            "research/experiments",
            "research/results",
            "scripts",
        )

        missing = [path for path in required_directories if not (PROJECT_ROOT / path).is_dir()]
        self.assertEqual([], missing, f"Missing required directories: {missing}")

    def test_current_dashboard_inputs_remain_available(self) -> None:
        self.assertTrue((PROJECT_ROOT / "app/dashboard.py").is_file())
        self.assertTrue((PROJECT_ROOT / "data/final_dataset.csv").is_file())


if __name__ == "__main__":
    unittest.main()

