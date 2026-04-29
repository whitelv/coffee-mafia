#!/usr/bin/env python3
"""Idempotent database seeder. Safe to run multiple times."""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

USERS = [
    {"rfid_uid": "ADMIN001", "name": "Admin", "role": "admin"},
    {"rfid_uid": "CLIENT001", "name": "Barista 1", "role": "client"},
]

RECIPES = [
    {
        "name": "Espresso",
        "description": "Classic single espresso shot pulled at 9 bar pressure.",
        "active": True,
        "steps": [
            {"order": 0, "type": "instruction", "label": "Prepare portafilter",
             "instruction_text": "Remove portafilter and knock out any old puck. Rinse with hot water."},
            {"order": 1, "type": "weight", "label": "Dose ground coffee",
             "target_value": 18.0, "tolerance": 0.5},
            {"order": 2, "type": "instruction", "label": "Tamp",
             "instruction_text": "Tamp with 20 kg pressure. Ensure a level, even tamp."},
            {"order": 3, "type": "weight", "label": "Extract espresso",
             "target_value": 36.0, "tolerance": 1.0},
            {"order": 4, "type": "timer", "label": "Wait for bloom",
             "target_value": 5},
        ],
    },
    {
        "name": "Americano",
        "description": "Espresso diluted with hot water for a milder, larger drink.",
        "active": True,
        "steps": [
            {"order": 0, "type": "instruction", "label": "Prepare cup",
             "instruction_text": "Pre-heat cup with hot water, then discard."},
            {"order": 1, "type": "weight", "label": "Dose ground coffee",
             "target_value": 18.0, "tolerance": 0.5},
            {"order": 2, "type": "instruction", "label": "Tamp",
             "instruction_text": "Tamp firmly and evenly with 20 kg pressure."},
            {"order": 3, "type": "weight", "label": "Pull espresso shot",
             "target_value": 36.0, "tolerance": 1.0},
            {"order": 4, "type": "weight", "label": "Add hot water",
             "target_value": 200.0, "tolerance": 10.0},
        ],
    },
    {
        "name": "Latte",
        "description": "Espresso with steamed milk and a thin layer of microfoam.",
        "active": True,
        "steps": [
            {"order": 0, "type": "instruction", "label": "Prepare portafilter",
             "instruction_text": "Rinse portafilter, ensure basket is clean and dry."},
            {"order": 1, "type": "weight", "label": "Dose ground coffee",
             "target_value": 18.0, "tolerance": 0.5},
            {"order": 2, "type": "instruction", "label": "Tamp",
             "instruction_text": "Tamp evenly. Lock portafilter into group head."},
            {"order": 3, "type": "weight", "label": "Pull espresso shot",
             "target_value": 36.0, "tolerance": 1.0},
            {"order": 4, "type": "instruction", "label": "Steam milk",
             "instruction_text": "Steam 200 ml whole milk to 65°C with silky microfoam texture."},
            {"order": 5, "type": "timer", "label": "Rest steamed milk",
             "target_value": 10},
            {"order": 6, "type": "weight", "label": "Pour steamed milk",
             "target_value": 320.0, "tolerance": 20.0},
        ],
    },
    {
        "name": "Cappuccino",
        "description": "Equal parts espresso, steamed milk, and dense microfoam.",
        "active": True,
        "steps": [
            {"order": 0, "type": "instruction", "label": "Prepare portafilter",
             "instruction_text": "Ensure portafilter basket is dry. Use fresh medium-fine grind."},
            {"order": 1, "type": "weight", "label": "Dose ground coffee",
             "target_value": 18.0, "tolerance": 0.5},
            {"order": 2, "type": "instruction", "label": "Tamp",
             "instruction_text": "Level and tamp with firm, even pressure."},
            {"order": 3, "type": "weight", "label": "Pull espresso shot",
             "target_value": 36.0, "tolerance": 1.0},
            {"order": 4, "type": "instruction", "label": "Steam milk",
             "instruction_text": "Steam 120 ml whole milk to 65°C with thick, dense foam."},
            {"order": 5, "type": "timer", "label": "Rest steamed milk",
             "target_value": 15},
            {"order": 6, "type": "weight", "label": "Pour milk and foam",
             "target_value": 180.0, "tolerance": 10.0},
        ],
    },
    {
        "name": "Flat White",
        "description": "Ristretto shots topped with velvety microfoam — stronger than a latte.",
        "active": True,
        "steps": [
            {"order": 0, "type": "instruction", "label": "Prepare portafilter",
             "instruction_text": "Use extra-fine grind for ristretto. Rinse group head."},
            {"order": 1, "type": "weight", "label": "Dose ground coffee",
             "target_value": 20.0, "tolerance": 0.5},
            {"order": 2, "type": "instruction", "label": "Tamp",
             "instruction_text": "Tamp with firm pressure. Ensure level tamp surface."},
            {"order": 3, "type": "weight", "label": "Pull ristretto shot",
             "target_value": 30.0, "tolerance": 1.0},
            {"order": 4, "type": "timer", "label": "Extraction time check",
             "target_value": 20},
            {"order": 5, "type": "instruction", "label": "Steam milk",
             "instruction_text": "Steam 120 ml whole milk to 60°C. Very fine, glossy microfoam."},
            {"order": 6, "type": "weight", "label": "Pour steamed milk",
             "target_value": 200.0, "tolerance": 10.0},
        ],
    },
]


async def seed():
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.db_name]

    # Seed users
    users_inserted = 0
    for user in USERS:
        result = await db.users.update_one(
            {"rfid_uid": user["rfid_uid"]},
            {"$setOnInsert": {**user, "created_at": datetime.utcnow()}},
            upsert=True,
        )
        if result.upserted_id:
            users_inserted += 1

    # Seed recipes
    recipes_inserted = 0
    for recipe in RECIPES:
        result = await db.recipes.update_one(
            {"name": recipe["name"]},
            {"$setOnInsert": {**recipe, "created_at": datetime.utcnow()}},
            upsert=True,
        )
        if result.upserted_id:
            recipes_inserted += 1

    print(f"Seed complete: {users_inserted} users inserted, {recipes_inserted} recipes inserted.")
    print(f"(Existing records were left unchanged.)")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
