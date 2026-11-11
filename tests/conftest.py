import os
import tempfile

# La base de datos de pruebas es temporal: debe fijarse ANTES de importar la app.
_tmp = tempfile.mkdtemp(prefix="miyjo_test_")
os.environ["MIYJO_DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["MIYJO_DEMO"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fresh():
    """Cliente nuevo (sin cookies) por prueba."""
    with TestClient(app) as c:
        yield c
