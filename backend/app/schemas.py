from datetime import datetime
from typing import Optional
from typing import Literal
from pydantic import BaseModel, HttpUrl, Field
from .models import JobStatus


class CreateJobRequest(BaseModel):
    url: HttpUrl = Field(..., description="Bilibili video page URL")
    provider: Literal["openai", "bailian"] = Field(
        default="openai", description="ASR provider to use"
    )


class JobResponse(BaseModel):
    id: str
    url: str
    provider: str
    status: JobStatus
    raw_text: Optional[str] = None
    formatted_text: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobsResponse(BaseModel):
    jobs: list[JobResponse]
