"""Validation error sanitization through the real handler, without persistence."""

import httpx
import pytest
from fastapi import FastAPI
from pydantic import field_validator

from app.api.errors import install_handlers
from app.api.schemas import Credentials, Input


class Envelope(Input):
    credentials: list[Credentials]


class RejectedPassword(Input):
    password: str

    @field_validator("password")
    @classmethod
    def reject(cls, value):
        raise ValueError("private-password-validator-context")


@pytest.fixture
async def validation_client():
    app = FastAPI()
    install_handlers(app)

    @app.post("/nested")
    async def nested(data: Envelope):
        pytest.fail("Invalid nested credentials reached the endpoint")

    @app.post("/validator")
    async def validator(data: RejectedPassword):
        pytest.fail("Rejected password reached the endpoint")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://app.test"
    ) as client:
        yield client


async def test_nested_unknown_key_is_removed_but_known_fields_and_numeric_indexes_remain(
    validation_client,
):
    response = await validation_client.post(
        "/nested",
        json={
            "credentials": [
                {
                    "email": "private-invalid-email",
                    "password": "secret",
                    "private-unknown-key": {"private-nested-key": "private-nested-value"},
                }
            ]
        },
    )
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert {"field": "body.credentials.0", "type": "extra_forbidden"} in details
    assert {"field": "body.credentials.0.password", "type": "string_too_short"} in details
    assert {"field": "body.credentials.0.email", "type": "value_error"} in details
    for private in ["private-", "secret"]:
        assert private not in response.text


async def test_validator_input_message_and_context_are_never_serialized(validation_client):
    response = await validation_client.post("/validator", json={"password": "private-input-value"})
    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {"field": "body.password", "type": "value_error"}
    ]
    assert "private-" not in response.text


async def test_json_parse_error_keeps_numeric_location_without_echoing_input(validation_client):
    response = await validation_client.post(
        "/nested",
        content='{"credentials": [private-json}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    detail = response.json()["error"]["details"][0]
    assert detail["type"] == "json_invalid"
    prefix, index = detail["field"].split(".")
    assert prefix == "body" and index.isdigit()
    assert "private-json" not in response.text
