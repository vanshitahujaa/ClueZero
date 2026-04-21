"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SubmitRequest(BaseModel):
    """Request payload for submitting a screenshot. User identified by Bearer token."""
    image: str = Field(..., description="Base64-encoded image data")
    prompt: Optional[str] = Field(default=None)


class SubmitResponse(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.QUEUED


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    response: Optional[str] = None
    error: Optional[str] = None
