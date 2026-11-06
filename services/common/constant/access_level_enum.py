from enum import Enum


class AccessLevel(str, Enum):
    ADMIN = "admin"
    QC_USER = "qc_user"
    PUBLISHER = "publisher"
