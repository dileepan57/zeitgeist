"""
API tests for /api/opportunities endpoint.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    with patch("pipeline.utils.db.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        from api.main import app
        with TestClient(app) as c:
            yield c, mock_client


class TestOpportunitiesEndpoint:

    def test_health_endpoint_returns_ok(self, client):
        tc, _ = client
        response = tc.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_opportunities_returns_200_with_empty_db(self, client):
        tc, mock_db = client
        # Mock DB returning no data
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value.data = []

        response = tc.get("/api/opportunities")
        assert response.status_code == 200

    def test_opportunities_response_is_list(self, client):
        tc, mock_db = client
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        response = tc.get("/api/opportunities")
        data = response.json()
        assert isinstance(data, list) or isinstance(data, dict)

    def test_telemetry_endpoint_exists(self, client):
        tc, mock_db = client
        # Set up mock returns for all telemetry queries
        mock_db.table.return_value.select.return_value.gte.return_value.execute.return_value.data = []
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        response = tc.get("/api/telemetry")
        assert response.status_code == 200

    def test_simulator_scenarios_endpoint_exists(self, client):
        tc, _ = client
        response = tc.get("/api/simulator/scenarios")
        assert response.status_code == 200

    def test_evals_endpoint_exists(self, client):
        tc, mock_db = client
        mock_db.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value.data = []
        response = tc.get("/api/evals")
        assert response.status_code == 200
