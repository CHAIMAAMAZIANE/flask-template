import os

import pytest
import requests


@pytest.mark.integration
def test_auth_api_end_to_end():
    auth_url = os.getenv("AUTH_URL", "http://localhost:5001")
    api_url = os.getenv("API_URL", "http://localhost:5002")

    try:
        login = requests.post(
            f"{auth_url}/auth/login",
            json={"username": "alice", "password": "password"},
            timeout=5,
        )
    except requests.RequestException as exc:
        pytest.skip(f"Integration services not available: {exc}")

    assert login.status_code == 200
    token = login.json()["access_token"]

    profile = requests.get(
        f"{api_url}/profile",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )
    assert profile.status_code == 200
    assert profile.json()["username"] == "alice"
