from ....common.constant import StitchTextMode
from pydantic import BaseModel


class StitchIssueRequest(BaseModel):
    text_mode: StitchTextMode = StitchTextMode.INVISIBLE


class StitchIssueRead(BaseModel):
    issue_id: int
    page_count: int
    filename: str
    download_url: str
    download_url_expires_in: int
    text_mode: StitchTextMode
