from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class IssueSummary(BaseModel):
    id: int
    issue_code: str
    issue_s3_key: str | None
    manifest_s3_key: str | None
    page_count: int


class VolumeWithIssues(BaseModel):
    id: int
    volume_code: str
    created_at: datetime
    issues: list[IssueSummary]


class PageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    issue_id: int
    page_number: int
    status: str
    is_check_page: bool
    current_approved_revision_id: int | None
    created_at: datetime
    updated_at: datetime
