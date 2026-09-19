"""Unit tests for the exception handlers (presentation/api/errors.py)."""

import pytest
from app.entities.errors import HumanCheckFailed, InvalidSessionToken, SessionMessageLimitExceeded
from app.main import app
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (InvalidSessionToken("x"), 401),
        (HumanCheckFailed("x"), 403),
        (SessionMessageLimitExceeded("x"), 429),
    ],
)
def test_domain_errors_map_to_http_status(error, status) -> None:
    async def boom() -> None:
        raise error

    path = f"/__test_errors/{status}"
    app.add_api_route(path, boom)
    try:
        response = TestClient(app).get(path)
    finally:
        app.router.routes.pop()

    assert response.status_code == status
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"
