from enum import Enum
from datetime import datetime
class FilePathsEnum(Enum):
    ISSUE_PATH = "derived/pdf/V1/i1"
    REVISION_PATH = "ocr/revisions/{volume}/{issue}/{page_number}"

    @classmethod
    def get_revision_path(
        cls,
        volume: str,
        issue: str,
        page_number: int | str,
        user_id: int | str,
    ) -> str:
        now = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

        rev_path = (
            cls.REVISION_PATH.value.replace("{volume}", str(volume))
            .replace("{issue}", str(issue))
            .replace("{page_number}", str(page_number))
        )
        return f"{rev_path}/{now}_{user_id}.json"
 