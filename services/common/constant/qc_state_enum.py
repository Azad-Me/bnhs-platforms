from enum import Enum


class QCState(str, Enum):
    UNVERIFIED = "unverified"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    NEEDS_CHANGES = "needs_changes"
    COMPLETED = "completed"
