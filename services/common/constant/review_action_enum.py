from enum import Enum


class ReviewAction(str, Enum):
    SEND_BACK = "send_back"
    APPROVE = "approve"
