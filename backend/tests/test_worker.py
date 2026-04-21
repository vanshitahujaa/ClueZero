"""Tests for the RQ worker task."""

from unittest.mock import patch, MagicMock

import pytest

from app.queue.worker import process_screenshot


class TestProcessScreenshot:
    @patch("app.queue.worker.store_dedup")
    @patch("app.queue.worker.get_provider")
    @patch("app.queue.worker.redis_lib.Redis.from_url")
    def test_successful_processing(self, mock_from_url, mock_get_provider, mock_dedup):
        """Worker should call LLM, store result, and cache dedup."""
        mock_redis = MagicMock()
        mock_from_url.return_value = mock_redis

        mock_provider = MagicMock()
        mock_provider.analyze_image.return_value = "This is a test response"
        mock_get_provider.return_value = mock_provider

        process_screenshot(
            job_id="test-job-1",
            image_b64="fake_b64_data",
            prompt="Test prompt",
            image_hash="abc123",
        )

        # Should have set status to processing, then completed
        calls = mock_redis.setex.call_args_list
        status_calls = [c for c in calls if "status" in str(c)]
        assert len(status_calls) == 2  # processing + completed

        # Should have stored the result
        result_calls = [c for c in calls if "result" in str(c)]
        assert len(result_calls) == 1

        # Should have cached for dedup
        mock_dedup.assert_called_once()

        # Should have called the LLM
        mock_provider.analyze_image.assert_called_once_with("fake_b64_data", "Test prompt")

    @patch("app.queue.worker.get_provider")
    @patch("app.queue.worker.redis_lib.Redis.from_url")
    def test_llm_failure(self, mock_from_url, mock_get_provider):
        """Worker should store error on LLM failure."""
        mock_redis = MagicMock()
        mock_from_url.return_value = mock_redis

        mock_provider = MagicMock()
        mock_provider.analyze_image.side_effect = RuntimeError("LLM API error")
        mock_get_provider.return_value = mock_provider

        with pytest.raises(RuntimeError, match="LLM API error"):
            process_screenshot(
                job_id="test-job-fail",
                image_b64="fake_b64",
                prompt="Test",
                image_hash="def456",
            )

        # Should have stored the error
        error_calls = [c for c in mock_redis.setex.call_args_list if "error" in str(c)]
        assert len(error_calls) == 1

        # Status should be "failed"
        status_calls = [c for c in mock_redis.setex.call_args_list if "failed" in str(c)]
        assert len(status_calls) == 1
