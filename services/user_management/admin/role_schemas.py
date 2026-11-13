from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    created_at: datetime
    updated_at: datetime
