from enum import Enum


class ReviewDecision(str, Enum):
    SUBMITTED = "submitted"
    SENT_BACK = "sent_back"
    APPROVED = "approved"
