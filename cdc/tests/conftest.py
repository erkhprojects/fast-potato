from __future__ import annotations

import os
import time

import psycopg
import pytest
from pymongo import MongoClient

_POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://fastpotato:fastpotato@localhost:5432/fastpotato",
)
_MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017/?replicaSet=rs0",
)


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    for _ in range(30):
        try:
            conn = psycopg.connect(_POSTGRES_DSN)
            conn.close()
            return _POSTGRES_DSN
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Postgres not reachable at {_POSTGRES_DSN}")


@pytest.fixture(scope="session")
def mongo_uri() -> str:
    # depends_on ensures mongo-init has run, but primary election still needs ~2s
    for _ in range(30):
        try:
            client = MongoClient(_MONGO_URI, serverSelectionTimeoutMS=2000)
            status = client.admin.command("replSetGetStatus")
            client.close()
            if status.get("ok") == 1.0:
                return _MONGO_URI
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"MongoDB replica set not ready at {_MONGO_URI}")
