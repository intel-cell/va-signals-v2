"""Test that ML scoring API routes are registered in the dashboard."""
from fastapi.testclient import TestClient


def test_ml_routes_registered():
    """ML router should be included in the main FastAPI app."""
    from src.dashboard_api import app
    route_paths = [r.path for r in app.routes]
    assert "/api/ml/score" in route_paths, "ML score endpoint not registered"
    assert "/api/ml/config" in route_paths, "ML config endpoint not registered"
    assert "/api/ml/stats" in route_paths, "ML stats endpoint not registered"
