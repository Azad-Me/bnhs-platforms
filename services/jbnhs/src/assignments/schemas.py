from datetime import datetime

from pydantic import BaseModel

from ....common.constant.qc_state_enum import QCState


class PageClaimRead(BaseModel):
    page_id: int
    status: QCState
    lock_expires_at: datetime
