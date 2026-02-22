"""
Basic tests for the Flask app.
Run: cd app && python -m pytest tests/ -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app


def test_index_returns_200():
    """Test that the index route responds."""
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200


def test_index_returns_json():
    """Test that index returns JSON with status field."""
    client = app.test_client()
    response = client.get('/')
    data = response.get_json()
    assert 'status' in data
    assert data['status'] == 'success'


def test_health_endpoint_exists():
    """Test that /health endpoint exists."""
    client = app.test_client()
    response = client.get('/health')
    # Will be 200 or 500 depending on DB — both are valid responses
    assert response.status_code in [200, 500]


def test_metrics_endpoint():
    """Test that /metrics endpoint exists (Prometheus)."""
    client = app.test_client()
    response = client.get('/metrics')
    assert response.status_code == 200
