import pytest
from fastapi.testclient import TestClient

from chatbot.api.app import app


@pytest.fixture
def test_client():
    return TestClient(app)
