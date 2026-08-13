from unittest import TestCase

from trendscope.benchmark import evaluate_scoring_calibration


class ScoringCalibrationTests(TestCase):
    def test_fixed_50_case_fixture_keeps_all_tiers_reachable(self):
        result = evaluate_scoring_calibration()
        self.assertEqual(result["case_count"], 50)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["confusion_matrix"]["high_value->high_value"], 10)
        self.assertEqual(result["confusion_matrix"]["watchlist->watchlist"], 15)
        self.assertEqual(result["confusion_matrix"]["candidate->candidate"], 25)
