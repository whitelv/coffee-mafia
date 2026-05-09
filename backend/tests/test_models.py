import pytest
from pydantic import ValidationError
from datetime import datetime

from backend.models.user import UserModel, UserPublic, UserCreate
from backend.models.session import BrewSessionModel, SessionCreate
from backend.models.recipe import RecipeStep, RecipeModel, RecipeCreate, RecipeUpdate
from backend.models.history import HistoryModel


# --- UserModel ---

def test_user_model_valid():
    u = UserModel(rfid_uid="AABBCCDD", name="Alice", role="client")
    assert u.name == "Alice"
    assert u.role == "client"


def test_user_model_invalid_role():
    with pytest.raises(ValidationError):
        UserModel(rfid_uid="XX", name="Bob", role="superuser")


def test_user_create_default_role():
    u = UserCreate(rfid_uid="XX", name="Bob")
    assert u.role == "client"


def test_user_public_serialization():
    u = UserPublic(id="abc", name="Alice", role="admin")
    assert u.role == "admin"


# --- RecipeStep ---

def test_recipe_step_weight_valid():
    s = RecipeStep(order=0, type="weight", label="Add water", target_value=200.0, tolerance=5.0)
    assert s.target_value == 200.0


def test_recipe_step_weight_missing_tolerance():
    with pytest.raises(ValidationError):
        RecipeStep(order=0, type="weight", label="Add water", target_value=200.0)


def test_recipe_step_weight_missing_target():
    with pytest.raises(ValidationError):
        RecipeStep(order=0, type="weight", label="Add water", tolerance=5.0)


def test_recipe_step_timer_valid():
    s = RecipeStep(order=1, type="timer", label="Wait", target_value=30.0)
    assert s.target_value == 30.0


def test_recipe_step_timer_missing_target():
    with pytest.raises(ValidationError):
        RecipeStep(order=1, type="timer", label="Wait")


def test_recipe_step_instruction_valid():
    s = RecipeStep(order=2, type="instruction", label="Grind", instruction_text="Grind beans finely")
    assert s.instruction_text == "Grind beans finely"


def test_recipe_step_instruction_no_target_needed():
    s = RecipeStep(order=0, type="instruction", label="Note", instruction_text="Do this")
    assert s.target_value is None
    assert s.tolerance is None


# --- RecipeModel ---

def test_recipe_model_valid():
    r = RecipeModel(
        name="Espresso",
        description="Classic shot",
        steps=[RecipeStep(order=0, type="instruction", label="Prepare", instruction_text="Ready")],
    )
    assert r.active is True
    assert len(r.steps) == 1


def test_recipe_update_partial():
    u = RecipeUpdate(name="New Name")
    assert u.name == "New Name"
    assert u.description is None
    assert u.active is None


# --- BrewSessionModel ---

def test_brew_session_defaults():
    s = BrewSessionModel(user_id="u1", recipe_id="r1", esp_id="ESP32_BAR_01")
    assert s.status == "active"
    assert s.current_step == 0
    assert s.completed_at is None


def test_brew_session_status_values():
    for status in ["active", "completed", "abandoned", "discarded"]:
        s = BrewSessionModel(user_id="u1", recipe_id="r1", esp_id="esp1", status=status)
        assert s.status == status


def test_brew_session_invalid_status():
    with pytest.raises(ValidationError):
        BrewSessionModel(user_id="u1", recipe_id="r1", esp_id="esp1", status="unknown")


def test_session_create():
    s = SessionCreate(recipe_id="r1", esp_id="esp1")
    assert s.recipe_id == "r1"


# --- HistoryModel ---

def test_history_model_valid():
    now = datetime.utcnow()
    h = HistoryModel(
        session_id="s1",
        user_id="u1",
        recipe_id="r1",
        recipe_name="Espresso",
        worker_name="Alice",
        cooked_by_admin=False,
        started_at=now,
        completed_at=now,
    )
    assert h.cooked_by_admin is False
