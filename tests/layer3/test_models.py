"""
Unit tests for Pydantic API models.
"""

import pytest
from pydantic import ValidationError

from vagus.layer3.api.models import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatus,
    TaskStatusResponse,
)


class TestTaskCreateRequest:

    def test_valid_request(self):
        req = TaskCreateRequest(prompt="Hello")
        assert req.prompt == "Hello"
        assert req.task_type == "default"
        assert req.stream is False
        assert req.metadata is None

    def test_empty_prompt_rejected(self):
        with pytest.raises(ValidationError):
            TaskCreateRequest(prompt="")

    def test_custom_task_type(self):
        req = TaskCreateRequest(prompt="Test", task_type="research")
        assert req.task_type == "research"

    def test_with_metadata(self):
        req = TaskCreateRequest(prompt="Test", metadata={"key": "value"})
        assert req.metadata == {"key": "value"}


class TestTaskStatus:

    def test_status_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
