from pydantic import BaseModel


class DashboardSummary(BaseModel):
    volume_count: int
    issue_count: int
    page_count: int
    completed_page_count: int
    in_review_page_count: int
    unverified_page_count: int
    completion_percent: float
