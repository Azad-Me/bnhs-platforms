from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ....common.constant.qc_state_enum import QCState


class PageClaimState(BaseModel):
    is_claimed: bool
    claimed_by_me: bool
    lock_expires_at: datetime | None


class QCPageRead(BaseModel):
    id: int
    issue_id: int
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
