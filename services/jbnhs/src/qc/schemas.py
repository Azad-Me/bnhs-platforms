from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class RevisionReviewEvent(BaseModel):
    decision: Literal["submitted", "sent_back", "approved"]
    actor_id: int
    actor_name: str
    note: str | None
    acted_at: datetime


class RevisionHistoryItem(BaseModel):
    id: int | None
    page_id: int
    based_on_revision_id: int | None
    saved_at: datetime | None
    saved_by: int | None
    author_name: str | None
    source: Literal["ocr", "revision"]
    is_approved: bool
    review_events: list[RevisionReviewEvent] = Field(default_factory=list)


class RevisionDocumentRead(BaseModel):
    id: int
    page_id: int
    based_on_revision_id: int | None
    saved_at: datetime
    saved_by: int
    author_name: str
    corrected_text: str
    document: dict[str, Any] | None


class RevisionComparisonRead(BaseModel):
    page_id: int
    revision_id: int
    against_revision_id: int | None
    base_source: Literal["ocr", "revision"]
    added_lines: int
    removed_lines: int
    unified_diff: list[str]
