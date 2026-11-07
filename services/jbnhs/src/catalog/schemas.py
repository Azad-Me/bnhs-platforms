from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ....common.constant.qc_state_enum import QCState


class IssueSummary(BaseModel):
    id: int
    issue_code: str
    toned_pdf_s3_key: str | None
    manifest_s3_key: str | None
    page_count: int
    completed_page_count: int
    in_review_page_count: int
    unverified_page_count: int
    completion_percent: float


class VolumeWithIssues(BaseModel):
    id: int
    volume_code: str
    created_at: datetime
    page_count: int
    completed_page_count: int
    in_review_page_count: int
    unverified_page_count: int
    completion_percent: float
    issues: list[IssueSummary]


class PageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    issue_id: int
    page_number: int
    status: QCState
    # is_check_page: bool
    # current_approved_revision_id: int | None
    created_at: datetime
    updated_at: datetime
