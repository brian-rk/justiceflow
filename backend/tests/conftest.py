import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="jf_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["JF_MODEL_DIR"] = str(_tmp / "models")
os.environ["JF_AS_OF"] = "2026-09-26"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import DEMO_PASSWORD, seed  # noqa: E402


@pytest.fixture(scope="session")
def client():
    seed(2500, history=True, seed_value=3)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    tokens = {}

    def headers(username):
        if username not in tokens:
            r = client.post("/api/auth/login", data={"username": username, "password": DEMO_PASSWORD})
            assert r.status_code == 200, r.text
            tokens[username] = r.json()["access_token"]
        return {"Authorization": f"Bearer {tokens[username]}"}
    return headers
