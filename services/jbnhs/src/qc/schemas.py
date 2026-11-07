from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ....common.constant.qc_state_enum import QCState


class PageClaimState(BaseModel):
    is_claimed: bool
    claimed_by_me: bool
    lock_expires_at: datetime | None


class QCPageRead(BaseModel):
    id: int
    issue_id: int
    volume_id: int | None = None
    volume_code: str | None = None
    issue_code: str | None = None
    page_number: int
    status: QCState
    is_check_page: bool
    ocr_text: str | None
    corrected_text: str
    current_revision_id: int | None
    revision_saved_at: datetime | None
    scan_url: str
    scan_url_expires_in: int
    claim: PageClaimState
    document: dict[str, Any] | None = None


class SaveRevisionRequest(BaseModel):
    base_revision_id: int | None
    document: dict[str, Any]


class PageRevisionRead(BaseModel):
    id: int
    page_id: int
    based_on_revision_id: int | None
    saved_at: datetime
    document: dict[str, Any]
    realignment_warnings: list[str] = Field(default_factory=list)
