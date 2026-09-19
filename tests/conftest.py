"""Test fixtures.

Tests run against a real PostgreSQL. By default a throwaway in-memory PGlite
server is started from `dev_db/server.js` (needs Node.js + `npm install` in
dev_db/). Set TEST_DATABASE_URL to use another PostgreSQL instead.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import db as core_db  # noqa: E402
from core.config import Settings  # noqa: E402
from core.models import Base  # noqa: E402

TEST_PORT = 55433


def _wait_for_port(port: int, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    raise RuntimeError(f"Test database did not start on port {port}")


@pytest.fixture(scope="session")
def database_url() -> str:
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return
    node = shutil.which("node")
    if node is None or not (ROOT / "dev_db" / "node_modules").exists():
        pytest.skip("Node.js + `npm install` in dev_db/ are required for database tests")
    proc = subprocess.Popen(
        [node, "server.js"],
        cwd=ROOT / "dev_db",
        env={**os.environ, "PGLITE_PORT": str(TEST_PORT), "PGLITE_MEMORY": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(TEST_PORT)
        yield f"postgresql://postgres:postgres@127.0.0.1:{TEST_PORT}/postgres?sslmode=disable"
    finally:
        proc.kill()


@pytest.fixture(autouse=True)
def fresh_db(database_url: str):
    """Point the app at the test database and start every test with empty tables."""
    core_db.reset_engine()
    settings = Settings(database_url=database_url, admin_emails=("admin@example.com",))
    engine = core_db.get_engine(settings)
    Base.metadata.drop_all(engine)
    core_db.init_db(settings)
    yield settings
    core_db.reset_engine()
