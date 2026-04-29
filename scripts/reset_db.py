#!/usr/bin/env python3
"""Drop all collections and re-seed. Irreversible — asks for confirmation."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from motor.motor_asyncio import AsyncIOMotorClient
from config import settings


async def reset():
    confirm = input("This will DELETE ALL DATA in the database. Type YES to confirm: ").strip()
    if confirm != "YES":
        print("Aborted.")
        sys.exit(0)

    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.db_name]

    for collection in ["users", "recipes", "brew_sessions", "history"]:
        result = await db[collection].delete_many({})
        print(f"Dropped {result.deleted_count} documents from '{collection}'")

    client.close()
    print("All collections cleared. Running seed_db.py...")

    # Re-seed
    import importlib.util
    seed_path = os.path.join(os.path.dirname(__file__), "seed_db.py")
    spec = importlib.util.spec_from_file_location("seed_db", seed_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    await mod.seed()


if __name__ == "__main__":
    asyncio.run(reset())
