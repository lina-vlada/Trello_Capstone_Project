from uuid import uuid4
from fastapi import status
from tests.integration.conftest import APIClient


async def register_user(api: APIClient,*,email: str | None = None,password: str = "integration-password"):
    email = email or f"user-{uuid4().hex}@example.com"
    response = await api.post(
        "/auth/register",
        json_body={
            "first_name": "Integration",
            "last_name": "User",
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    return {**response.json(), "password": password}


async def login_user(api: APIClient, user: dict[str, str]):
    response = await api.post(
        "/auth/login",
        json_body={"email": user["email"], "password": user["password"]},
    )
    assert response.status_code == status.HTTP_200_OK
    tokens = response.json()
    return {
        **tokens,
        "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
    }


async def create_board(api: APIClient,headers: dict[str, str],*,name: str = "Integration board"):
    response = await api.post(
        "/boards/",
        json_body={"name": name, "description": "Integration test board"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


async def create_section(api: APIClient,headers: dict[str, str],board_id: int,*,name: str = "Integration section"):
    response = await api.post(
        f"/boards/{board_id}/sections/",
        json_body={"name": name, "description": "Integration test section"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()


async def create_ticket(api: APIClient,headers: dict[str, str],board_id: int,section_id: int,*,name: str = "Integration ticket",assignee_ids: list[int] | None = None):
    response = await api.post(
        f"/boards/{board_id}/sections/{section_id}/tickets/",
        json_body={
            "name": name,
            "description": "Integration test ticket",
            "assignee_ids": assignee_ids or [],
        },
        headers=headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()
