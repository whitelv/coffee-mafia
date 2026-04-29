from datetime import datetime
from typing import Annotated, Literal

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PyObjectId = Annotated[str, BeforeValidator(str)]


class UserModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId | None = Field(alias="_id", default=None)
    rfid_uid: str
    name: str
    role: Literal["client", "admin"]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserPublic(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId | None = Field(alias="_id", default=None)
    name: str
    role: Literal["client", "admin"]


class UserCreate(BaseModel):
    rfid_uid: str
    name: str
    role: Literal["client", "admin"] = "client"
