import pytest
from fastapi.testclient import TestClient

from sirep.app.api import app
from sirep.infra.runtime_credentials import (
    clear_all_credentials,
    get_gestao_base_password,
)


@pytest.fixture(autouse=True)
def _reset_credentials():
    clear_all_credentials()
    yield
    clear_all_credentials()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_store_and_clear_gestao_password(client: TestClient):
    response = client.post(
        "/session/gestao-base/password", json={"password": "SenhaSecreta!"}
    )
    assert response.status_code == 204
    assert get_gestao_base_password() == "SenhaSecreta!"

    response = client.delete("/session/gestao-base/password")
    assert response.status_code == 204
    assert get_gestao_base_password() is None


def test_store_gestao_password_rejects_blank(client: TestClient):
    response = client.post("/session/gestao-base/password", json={"password": "   "})
    assert response.status_code == 400
    payload = response.json()
    assert payload.get("detail") == "Senha obrigatória."
    assert get_gestao_base_password() is None
