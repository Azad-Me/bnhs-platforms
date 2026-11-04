from enum import Enum


class AccessLevel(str, Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
