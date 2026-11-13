from enum import Enum


class ReviewAction(str, Enum):
    SEND_BACK = "send_back"
    APPROVE = "approve"

    def __init__(self,arg):
        self.label = arg