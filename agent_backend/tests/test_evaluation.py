from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from trendscope.evaluation import human_dataset_status


class HumanEvaluationDatasetTests(TestCase):
    def test_empty_dataset_is_explicitly_not_ready(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("", encoding="utf-8")
            result = human_dataset_status(path)
        self.assertFalse(result["ready"])
        self.assertEqual(result["row_count"], 0)
        self.assertIn("禁止报告", result["message"])
