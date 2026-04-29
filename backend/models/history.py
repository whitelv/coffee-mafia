from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PyObjectId = Annotated[str, BeforeValidator(str)]


class HistoryModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId | None = Field(alias="_id", default=None)
    session_id: str
    user_id: str
    recipe_id: str
    recipe_name: str
    worker_name: str
    cooked_by_admin: bool
    started_at: datetime
    completed_at: datetime
