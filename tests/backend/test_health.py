from importlib.metadata import version

import pytest
from fastapi.testclient import TestClient

import backend.app as backend_app


def test_health_contract():
    with TestClient(backend_app.create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "ok": True,
        "data": {"service": "contexttrace-backend", "status": "running",
                 "version": version("contexttrace"), "api_version": 1},
        "error": None,
    }
    assert type(response.json()["data"]["api_version"]) is int


@pytest.mark.parametrize("method,path,status,code", [
    ("GET", "/missing", 404, "NOT_FOUND"),
    ("GET", "/health/", 404, "NOT_FOUND"),
    ("POST", "/health", 405, "METHOD_NOT_ALLOWED"),
    ("DELETE", "/health", 405, "METHOD_NOT_ALLOWED"),
])
def test_http_errors(method, path, status, code):
    with TestClient(backend_app.create_app()) as client:
        response = client.request(method, path)
        assert client.get("/health").status_code == 200
    assert response.status_code == status
    assert response.json()["ok"] is False
    assert response.json()["data"] is None
    assert response.json()["error"]["code"] == code
    if status == 405:
        assert "GET" in response.headers["allow"]


def test_internal_error_is_sanitized_and_recovers(monkeypatch):
    original = backend_app.get_health

    def broken_health():
        raise RuntimeError("secret-token /private/user/path")

    with TestClient(backend_app.create_app(), raise_server_exceptions=False) as client:
        monkeypatch.setattr(backend_app, "get_health", broken_health)
        response = client.get("/health")
        assert response.status_code == 500
        assert response.json() == {
            "ok": False, "data": None,
            "error": {"code": "INTERNAL_ERROR", "message": "상태 확인 중 오류가 발생했습니다."},
        }
        monkeypatch.setattr(backend_app, "get_health", original)
        assert client.get("/health").status_code == 200


def test_validation_error_contract():
    app = backend_app.create_app()

    @app.get("/test-only")
    def validated(count: int):
        return count

    with TestClient(app) as client:
        response = client.get("/test-only?count=private-input")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "private-input" not in response.text
