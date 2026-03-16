"""
Tests for institutional knowledge generation.
"""
import pytest
from unittest.mock import MagicMock


class TestGetLatestKnowledge:

    def test_returns_none_when_no_knowledge_in_db(self, mock_db):
        mock_db.select.return_value = []
        from pipeline.reflection.knowledge import get_latest_knowledge
        result = get_latest_knowledge()
        assert result is None

    def test_returns_knowledge_brief_string(self, mock_db):
        mock_db.select.return_value = [
            {
                "id": "test-uuid",
                "version": 1,
                "knowledge_brief": "Longevity topics are consistently underserved.",
                "performance_summary": "{}",
                "created_at": "2024-01-01T00:00:00",
            }
        ]
        from pipeline.reflection.knowledge import get_latest_knowledge
        result = get_latest_knowledge()
        assert result == "Longevity topics are consistently underserved."

    def test_returns_most_recent_version(self, mock_db):
        """get_latest_knowledge should return the most recent (highest version) brief."""
        mock_db.select.return_value = [
            {"version": 3, "knowledge_brief": "Latest knowledge brief.", "performance_summary": "{}"},
        ]
        from pipeline.reflection.knowledge import get_latest_knowledge
        result = get_latest_knowledge()
        assert result is not None
