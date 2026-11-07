from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from ....common.constant.qc_state_enum import QCState


class ReviewDecisionRequest(BaseModel):
    decision: Literal["send_back", "approve"]
    note: str | None = None

    @model_validator(mode="after")
    def require_send_back_note(self) -> ReviewDecisionRequest:
        if self.decision == "send_back" and not (self.note or "").strip():
            raise ValueError("A non-empty note is required when sending back.")
        if self.note is not None:
            self.note = self.note.strip() or None
        return self


class PageReviewActionRead(BaseModel):
    page_id: int
    status: QCState
    revision_id: int
    actor_id: int
    decision: Literal["submitted", "sent_back", "approved"]
    note: str | None
    acted_at: datetime
