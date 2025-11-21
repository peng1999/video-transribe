from enum import StrEnum
from datetime import datetime
from sqlalchemy import Column, DateTime, Enum, String, Text
from .db import Base


class JobStatus(StrEnum):
    pending = "pending"
    downloading = "downloading"
    transcribing = "transcribing"
    formatting = "formatting"
    done = "done"
    error = "error"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)
    url = Column(String, nullable=False)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    raw_text = Column(Text, nullable=True)
    formatted_text = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
