from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PyObjectId = Annotated[str, BeforeValidator(str)]


class BrewSessionModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId | None = Field(alias="_id", default=None)
    user_id: str
    recipe_id: str
    esp_id: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    status: Literal["active", "completed", "abandoned"] = "active"
    current_step: int = 0
    last_seen: datetime = Field(default_factory=datetime.utcnow)


class SessionCreate(BaseModel):
    recipe_id: str
    esp_id: str
