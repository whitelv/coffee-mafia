#!/usr/bin/env python3
"""
Generate a JWT token for a user identified by RFID UID.
Useful for testing without physical hardware.

Usage:
    python generate_jwt.py --rfid ADMIN001
    python generate_jwt.py --rfid CLIENT001
"""
import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from motor.motor_asyncio import AsyncIOMotorClient
from config import settings
from routers.auth import create_jwt


async def main(rfid_uid: str):
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.db_name]

    user = await db.users.find_one({"rfid_uid": rfid_uid})
    if not user:
        print(f"Error: No user found with rfid_uid='{rfid_uid}'", file=sys.stderr)
        sys.exit(1)

    user_id = str(user["_id"])
    token = create_jwt(user_id, user["name"], user["role"])

    print(f"User:  {user['name']} ({user['role']})")
    print(f"ID:    {user_id}")
    print(f"Token: {token}")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate JWT for a user by RFID UID")
    parser.add_argument("--rfid", required=True, help="RFID UID of the user (e.g. ADMIN001)")
    args = parser.parse_args()
    asyncio.run(main(args.rfid))
