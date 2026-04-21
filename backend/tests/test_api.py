"""Tests for API endpoints (submit, result, health)."""

import base64
import io
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import deps


def _make_test_image_b64() -> str:
    """Create a small test image and return base64."""
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture
def mock_redis():
    """A mock Redis client with sensible defaults."""
    r = MagicMock()
    r.ping.return_value = True
    r.exists.return_value = False  # no rate limit hit
    r.get.return_value = None       # no dedup cache / no result
    return r


@pytest.fixture
def client(mock_redis):
    """
    Create a FastAPI TestClient with Redis mocked.
    
    We patch redis.Redis.from_url (called in the lifespan) to return
    our mock, AND we also patch deps.set_redis to inject the SAME mock
    into deps so that get_redis() returns it during request handling.
    """
    with patch("app.main.redis.Redis.from_url", return_value=mock_redis):
        with patch("app.main.set_redis") as mock_set:
            # When set_redis is called during lifespan, inject our mock
            def _inject(conn):
                deps._redis_conn = mock_redis
            mock_set.side_effect = _inject

            from app.main import app
            with TestClient(app) as c:
                yield c, mock_redis

    deps._redis_conn = None


class TestHealthEndpoint:
    def test_health_ok(self, client):
        c, _ = client
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestSubmitEndpoint:
    @patch("app.routes.submit.Queue")
    def test_submit_success(self, mock_queue_cls, client):
        c, mock_redis = client
        mock_q = MagicMock()
        mock_queue_cls.return_value = mock_q

        image_b64 = _make_test_image_b64()
        resp = c.post("/submit", json={
            "image": image_b64,
            "user_id": "test-user",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        mock_q.enqueue.assert_called_once()

    def test_submit_missing_user_id(self, client):
        c, _ = client
        resp = c.post("/submit", json={
            "image": "abc",
        })
        assert resp.status_code == 422

    def test_submit_missing_image(self, client):
        c, _ = client
        resp = c.post("/submit", json={
            "user_id": "test",
        })
        assert resp.status_code == 422

    @patch("app.routes.submit.check_rate_limit")
    def test_submit_rate_limited(self, mock_rl, client):
        from fastapi import HTTPException
        mock_rl.side_effect = HTTPException(status_code=429, detail="Rate limited")

        c, _ = client
        resp = c.post("/submit", json={
            "image": _make_test_image_b64(),
            "user_id": "test",
        })
        assert resp.status_code == 429


class TestResultEndpoint:
    def test_result_not_found(self, client):
        c, mock_redis = client
        mock_redis.get.return_value = None
        resp = c.get("/result/nonexistent-job-id")
        assert resp.status_code == 404

    def test_result_completed(self, client):
        c, mock_redis = client

        def side_effect(key):
            if key == "job:test-job:status":
                return "completed"
            if key == "job:test-job:result":
                return "This is the AI response."
            return None

        mock_redis.get.side_effect = side_effect

        resp = c.get("/result/test-job")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["response"] == "This is the AI response."

    def test_result_pending(self, client):
        c, mock_redis = client

        def side_effect(key):
            if key == "job:test-job:status":
                return "queued"
            return None

        mock_redis.get.side_effect = side_effect

        resp = c.get("/result/test-job")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"
