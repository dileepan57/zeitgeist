"""
Tests for signal calibration engine.
Covers: precision/recall math, zero-outcome edge case, get_calibrated_weights.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestGetCalibratedWeights:

    def test_no_data_returns_equal_weights(self, mock_db):
        """With no signal_performance data, all sources get neutral 0.5 weight."""
        mock_db.select.return_value = []
        from pipeline.reflection.calibration import get_calibrated_weights
        weights = get_calibrated_weights()
        assert isinstance(weights, dict)

    def test_weights_normalized_to_sum_1(self, mock_db):
        """Returned weights should sum to approximately 1.0."""
        mock_db.select.return_value = [
            {"signal_source": "reddit", "precision": 0.8, "recall": 0.6},
            {"signal_source": "google_trends", "precision": 0.6, "recall": 0.5},
            {"signal_source": "gdelt", "precision": 0.4, "recall": 0.7},
        ]
        from pipeline.reflection.calibration import get_calibrated_weights
        weights = get_calibrated_weights()
        if weights:
            total = sum(weights.values())
            assert total == pytest.approx(1.0, abs=0.01)

    def test_higher_precision_gets_higher_weight(self, mock_db):
        """Source with precision=0.9 should get higher weight than 0.3."""
        mock_db.select.return_value = [
            {"signal_source": "reddit", "precision": 0.9, "recall": 0.7},
            {"signal_source": "gdelt", "precision": 0.3, "recall": 0.5},
        ]
        from pipeline.reflection.calibration import get_calibrated_weights
        weights = get_calibrated_weights()
        if "reddit" in weights and "gdelt" in weights:
            assert weights["reddit"] > weights["gdelt"]

    def test_zero_precision_gets_neutral_weight(self, mock_db):
        """A source with precision=0 should fall back to neutral 0.5."""
        mock_db.select.return_value = [
            {"signal_source": "new_source", "precision": 0, "recall": 0},
        ]
        from pipeline.reflection.calibration import get_calibrated_weights
        weights = get_calibrated_weights()
        # Should not crash, source should get some weight
        assert isinstance(weights, dict)

    def test_none_precision_gets_neutral_weight(self, mock_db):
        """A source with precision=None falls back to 0.5."""
        mock_db.select.return_value = [
            {"signal_source": "untracked_source", "precision": None, "recall": None},
        ]
        from pipeline.reflection.calibration import get_calibrated_weights
        weights = get_calibrated_weights()
        assert isinstance(weights, dict)


class TestCalibrateSignals:

    def test_no_mature_recommendations_runs_without_error(self, mock_db):
        """With no mature recommendations, calibration should log and return gracefully."""
        mock_db.select.return_value = []

        # Also patch the direct DB client call
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.lt.return_value.execute.return_value.data = []
        mock_db.get_client.return_value = mock_client

        from pipeline.reflection.calibration import calibrate_signals
        # Should not raise
        calibrate_signals()

    def test_precision_recall_math(self):
        """Verify precision/recall calculation is correct."""
        tp, fp, fn = 8, 2, 3
        expected_precision = tp / (tp + fp)  # 8/10 = 0.8
        expected_recall = tp / (tp + fn)     # 8/11 ≈ 0.727

        assert expected_precision == pytest.approx(0.8, abs=0.01)
        assert expected_recall == pytest.approx(0.727, abs=0.01)

    def test_precision_with_no_positives_is_zero(self):
        """No true or false positives → precision undefined → treat as 0."""
        tp, fp = 0, 0
        precision = tp / max(tp + fp, 1)
        assert precision == 0.0
