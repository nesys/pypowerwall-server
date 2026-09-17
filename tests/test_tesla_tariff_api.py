"""Tests for Tesla tariff and Time-of-Use cloud API routes."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.gateway_manager import gateway_manager
from app.main import app


_CONTROL_TOKEN = "test-secret-token"


@pytest.fixture
def tesla_client(monkeypatch):
    """Client with control authentication enabled for Tesla write-route tests."""
    monkeypatch.setattr(settings, "control_secret", _CONTROL_TOKEN)
    return TestClient(app)


def test_tesla_tariff_rate_requires_cloud_connection(tesla_client, monkeypatch):
    """GET fails fast when the dedicated Tesla cloud connection is unavailable."""
    monkeypatch.setattr(gateway_manager, "_cloud_control", None)

    response = tesla_client.get("/api/tesla/tariff_rate")

    assert response.status_code == 503
    assert response.json()["detail"] == "Tesla cloud control connection not available"


def test_tesla_tariff_rate_forwards_cloud_poll(tesla_client, monkeypatch):
    """GET forwards the tariff poll to the dedicated cloud-control connection."""
    expected = {"code": "GME-DYNAMIC", "energy_charges": {}}
    cloud_control = AsyncMock(return_value=expected)
    monkeypatch.setattr(gateway_manager, "_cloud_control", object())
    monkeypatch.setattr(gateway_manager, "cloud_control", cloud_control)

    response = tesla_client.get("/api/tesla/tariff_rate")

    assert response.status_code == 200
    assert response.json() == expected
    cloud_control.assert_awaited_once_with(
        "poll",
        "/api/tesla/tariff_rate",
        timeout=15.0,
    )


def test_tesla_tariff_rate_none_returns_503(tesla_client, monkeypatch):
    """A missing cloud response is exposed as service unavailable."""
    cloud_control = AsyncMock(return_value=None)
    monkeypatch.setattr(gateway_manager, "_cloud_control", object())
    monkeypatch.setattr(gateway_manager, "cloud_control", cloud_control)

    response = tesla_client.get("/api/tesla/tariff_rate")

    assert response.status_code == 503
    assert response.json()["detail"] == "Unable to retrieve Tesla tariff rate"


def test_tesla_tariff_rate_error_returns_502(tesla_client, monkeypatch):
    """Library-level cloud errors are translated to a bad-gateway response."""
    cloud_control = AsyncMock(return_value={"ERROR": "Tesla API failed"})
    monkeypatch.setattr(gateway_manager, "_cloud_control", object())
    monkeypatch.setattr(gateway_manager, "cloud_control", cloud_control)

    response = tesla_client.get("/api/tesla/tariff_rate")

    assert response.status_code == 502
    assert response.json()["detail"] == "Tesla API failed"


def test_tesla_tou_requires_cloud_connection(tesla_client, monkeypatch):
    """POST fails fast when cloud control is unavailable."""
    monkeypatch.setattr(gateway_manager, "_cloud_control", None)

    response = tesla_client.post(
        "/api/tesla/time_of_use_settings",
        json={"tou_settings": {}},
        headers={"Authorization": f"Bearer {_CONTROL_TOKEN}"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Tesla cloud control connection not available"


def test_tesla_tou_rejects_invalid_payload(tesla_client, monkeypatch):
    """POST requires tou_settings to be a JSON object."""
    monkeypatch.setattr(gateway_manager, "_cloud_control", object())

    for payload in ({}, {"tou_settings": None}, {"tou_settings": []}):
        response = tesla_client.post(
            "/api/tesla/time_of_use_settings",
            json=payload,
            headers={"Authorization": f"Bearer {_CONTROL_TOKEN}"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "'tou_settings' must be an object"


def test_tesla_tou_forwards_authenticated_post(tesla_client, monkeypatch):
    """POST forwards the complete payload through serialized cloud control."""
    payload = {
        "tou_settings": {
            "optimization_strategy": "economics",
            "tariff_content_v2": {"code": "GME-DYNAMIC"},
        }
    }
    expected = {"response": '{"Message":"Updated","Code":201}\n'}
    cloud_control = AsyncMock(return_value=expected)
    monkeypatch.setattr(gateway_manager, "_cloud_control", object())
    monkeypatch.setattr(gateway_manager, "cloud_control", cloud_control)

    response = tesla_client.post(
        "/api/tesla/time_of_use_settings",
        json=payload,
        headers={"Authorization": f"Bearer {_CONTROL_TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json() == expected
    cloud_control.assert_awaited_once_with(
        "post",
        "/api/tesla/time_of_use_settings",
        payload,
        timeout=20.0,
    )


def test_tesla_tou_none_returns_503(tesla_client, monkeypatch):
    """A missing write response is exposed as service unavailable."""
    cloud_control = AsyncMock(return_value=None)
    monkeypatch.setattr(gateway_manager, "_cloud_control", object())
    monkeypatch.setattr(gateway_manager, "cloud_control", cloud_control)

    response = tesla_client.post(
        "/api/tesla/time_of_use_settings",
        json={"tou_settings": {}},
        headers={"Authorization": f"Bearer {_CONTROL_TOKEN}"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Unable to update Tesla time-of-use settings"


def test_tesla_tou_error_returns_502(tesla_client, monkeypatch):
    """Library-level write errors are translated to a bad-gateway response."""
    cloud_control = AsyncMock(return_value={"ERROR": "Tesla API failed"})
    monkeypatch.setattr(gateway_manager, "_cloud_control", object())
    monkeypatch.setattr(gateway_manager, "cloud_control", cloud_control)

    response = tesla_client.post(
        "/api/tesla/time_of_use_settings",
        json={"tou_settings": {}},
        headers={"Authorization": f"Bearer {_CONTROL_TOKEN}"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Tesla API failed"
