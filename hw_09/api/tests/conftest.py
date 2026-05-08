import sys
from pathlib import Path

import pytest

# Чтобы pytest мог импортировать api.* из корня репо
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as c:
        yield c
