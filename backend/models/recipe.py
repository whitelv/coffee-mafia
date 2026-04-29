from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

PyObjectId = Annotated[str, BeforeValidator(str)]


class RecipeStep(BaseModel):
    order: int
    type: Literal["weight", "timer", "instruction"]
    label: str
    target_value: float | None = None
    tolerance: float | None = None
    instruction_text: str | None = None

    @model_validator(mode="after")
    def validate_step_fields(self) -> "RecipeStep":
        if self.type == "weight":
            if self.target_value is None or self.tolerance is None:
                raise ValueError("Weight steps require target_value and tolerance")
        elif self.type == "timer":
            if self.target_value is None:
                raise ValueError("Timer steps require target_value (seconds)")
        return self


class RecipeModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: PyObjectId | None = Field(alias="_id", default=None)
    name: str
    description: str
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    steps: list[RecipeStep]


class RecipeCreate(BaseModel):
    name: str
    description: str
    active: bool = True
    steps: list[RecipeStep]


class RecipeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    active: bool | None = None
    steps: list[RecipeStep] | None = None
