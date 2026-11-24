import pytest
from fastapi import status
from tests.integration.factories import (
    create_board,
    create_section,
    create_ticket,
    login_user,
    register_user,
)


async def _share_board(api, owner_tokens, member, member_tokens, role="editor"):
    board = await create_board(api, owner_tokens["headers"])
    invite = await api.post(
        f"/boards/{board['id']}/invites",
        json_body={"email": member["email"], "role": role},
        headers=owner_tokens["headers"],
    )
    assert invite.status_code == status.HTTP_201_CREATED
    accepted = await api.post(
        "/boards/invites/accept",
        json_body={"token": invite.json()["invitation_token"]},
        headers=member_tokens["headers"],
    )
    assert accepted.status_code == status.HTTP_200_OK
    return board


@pytest.mark.asyncio
async def test_ticket_create_get_update_assign_and_move(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    member = await register_user(api)
    member_tokens = await login_user(api, member)
    board = await _share_board(api, owner_tokens, member, member_tokens)
    first_section = await create_section(api, owner_tokens["headers"], board["id"])
    second_section = await create_section(
        api, owner_tokens["headers"], board["id"], name="In progress"
    )
    path = f"/boards/{board['id']}/sections/{first_section['id']}/tickets"

    created = await api.post(
        f"{path}/",
        json_body={
            "name": "First task",
            "description": "Work description",
            "assignee_ids": [owner["id"], member["id"], member["id"]],
        },
        headers=owner_tokens["headers"],
    )
    ticket_id = created.json()["id"]
    fetched = await api.get(f"{path}/{ticket_id}", headers=member_tokens["headers"])
    updated = await api.patch(
        f"{path}/{ticket_id}",
        json_body={"name": "Renamed task", "assignee_ids": [member["id"]]},
        headers=member_tokens["headers"],
    )
    moved = await api.patch(
        f"{path}/{ticket_id}",
        json_body={"section_id": second_section["id"]},
        headers=member_tokens["headers"],
    )
    old_section_lookup = await api.get(
        f"{path}/{ticket_id}", headers=owner_tokens["headers"]
    )
    new_section_lookup = await api.get(
        f"/boards/{board['id']}/sections/{second_section['id']}/tickets/{ticket_id}",
        headers=member_tokens["headers"],
    )

    assert created.status_code == status.HTTP_201_CREATED
    memberships = created.json()["memberships"]
    assert {(item["user_id"], item["role"]) for item in memberships} == {
        (owner["id"], "creator"),
        (member["id"], "member"),
    }
    assert fetched.status_code == status.HTTP_200_OK
    assert updated.status_code == status.HTTP_200_OK
    assert updated.json()["name"] == "Renamed task"
    assert [(item["user_id"], item["role"]) for item in updated.json()["memberships"]] == [
        (owner["id"], "creator"),
        (member["id"], "member"),
    ]
    assert moved.status_code == status.HTTP_200_OK
    assert moved.json()["section_id"] == second_section["id"]
    assert old_section_lookup.status_code == status.HTTP_404_NOT_FOUND
    assert new_section_lookup.status_code == status.HTTP_200_OK


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "description": "Valid"},
        {"name": "x" * 101, "description": "Valid"},
        {"name": "Valid", "description": ""},
        {"name": "Valid", "description": "x" * 301},
        {"name": "Valid"},
    ],
)
@pytest.mark.asyncio
async def test_ticket_creation_rejects_invalid_payload(api, payload):
    owner = await register_user(api)
    tokens = await login_user(api, owner)
    board = await create_board(api, tokens["headers"])
    section = await create_section(api, tokens["headers"], board["id"])

    response = await api.post(
        f"/boards/{board['id']}/sections/{section['id']}/tickets/",
        json_body=payload,
        headers=tokens["headers"],
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_ticket_assignees_must_belong_to_board(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    outsider = await register_user(api)
    board = await create_board(api, owner_tokens["headers"])
    section = await create_section(api, owner_tokens["headers"], board["id"])

    response = await api.post(
        f"/boards/{board['id']}/sections/{section['id']}/tickets/",
        json_body={
            "name": "Invalid assignment",
            "description": "Outsider is not a board member",
            "assignee_ids": [outsider["id"]],
        },
        headers=owner_tokens["headers"],
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == "All assignees must be members of the board"


@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({}, "Provide at least one field to update"),
        ({"name": None}, "Ticket name cannot be null"),
        ({"description": None}, "Ticket description cannot be null"),
        ({"assignee_ids": None}, "Assignee IDs cannot be null"),
        ({"section_id": None}, "Section ID cannot be null"),
    ],
)
@pytest.mark.asyncio
async def test_ticket_update_rejects_empty_or_null_fields(api, payload, detail):
    owner = await register_user(api)
    tokens = await login_user(api, owner)
    board = await create_board(api, tokens["headers"])
    section = await create_section(api, tokens["headers"], board["id"])
    ticket = await create_ticket(api, tokens["headers"], board["id"], section["id"])

    response = await api.patch(
        f"/boards/{board['id']}/sections/{section['id']}/tickets/{ticket['id']}",
        json_body=payload,
        headers=tokens["headers"],
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_ticket_update_rejects_invalid_assignees_and_target_section(api):
    owner = await register_user(api)
    tokens = await login_user(api, owner)
    outsider = await register_user(api)
    board = await create_board(api, tokens["headers"])
    section = await create_section(api, tokens["headers"], board["id"])
    ticket = await create_ticket(api, tokens["headers"], board["id"], section["id"])
    ticket_path = (
        f"/boards/{board['id']}/sections/{section['id']}/tickets/{ticket['id']}"
    )

    invalid_assignee = await api.patch(
        ticket_path,
        json_body={"assignee_ids": [outsider["id"]]},
        headers=tokens["headers"],
    )
    invalid_section = await api.patch(
        ticket_path,
        json_body={"section_id": 999999},
        headers=tokens["headers"],
    )

    assert invalid_assignee.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_section.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_section_response_lists_active_tickets_and_excludes_archived(api):
    owner = await register_user(api)
    tokens = await login_user(api, owner)
    board = await create_board(api, tokens["headers"])
    section = await create_section(api, tokens["headers"], board["id"])
    first = await create_ticket(
        api, tokens["headers"], board["id"], section["id"], name="First"
    )
    second = await create_ticket(
        api, tokens["headers"], board["id"], section["id"], name="Second"
    )
    base = f"/boards/{board['id']}/sections/{section['id']}/tickets"

    before_archive = await api.get(
        f"/boards/{board['id']}/sections/{section['id']}",
        headers=tokens["headers"],
    )
    archived = await api.delete(
        f"{base}/{first['id']}", headers=tokens["headers"]
    )
    after_archive = await api.get(
        f"/boards/{board['id']}/sections/{section['id']}",
        headers=tokens["headers"],
    )

    assert before_archive.status_code == status.HTTP_200_OK
    assert {item["id"] for item in before_archive.json()["tickets"]} == {
        first["id"],
        second["id"],
    }
    assert archived.status_code == status.HTTP_204_NO_CONTENT
    assert [item["id"] for item in after_archive.json()["tickets"]] == [second["id"]]


@pytest.mark.asyncio
async def test_ticket_archive_list_and_permanent_delete(api):
    owner = await register_user(api)
    tokens = await login_user(api, owner)
    board = await create_board(api, tokens["headers"])
    section = await create_section(api, tokens["headers"], board["id"])
    ticket = await create_ticket(api, tokens["headers"], board["id"], section["id"])
    base = f"/boards/{board['id']}/sections/{section['id']}/tickets/{ticket['id']}"

    premature_delete = await api.delete(f"{base}/permanent", headers=tokens["headers"])
    archived = await api.delete(base, headers=tokens["headers"])
    active_get = await api.get(base, headers=tokens["headers"])
    archived_list = await api.get(
        f"/boards/{board['id']}/sections/{section['id']}/tickets/archived",
        headers=tokens["headers"],
    )
    permanent_delete = await api.delete(
        f"{base}/permanent", headers=tokens["headers"]
    )
    missing_after_delete = await api.get(base, headers=tokens["headers"])

    assert premature_delete.status_code == status.HTTP_409_CONFLICT
    assert archived.status_code == status.HTTP_204_NO_CONTENT
    assert active_get.status_code == status.HTTP_404_NOT_FOUND
    assert [item["id"] for item in archived_list.json()] == [ticket["id"]]
    assert permanent_delete.status_code == status.HTTP_204_NO_CONTENT
    assert missing_after_delete.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_viewer_can_read_ticket_but_cannot_create_update_or_archive(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    viewer = await register_user(api)
    viewer_tokens = await login_user(api, viewer)
    board = await create_board(api, owner_tokens["headers"])
    invite = await api.post(
        f"/boards/{board['id']}/invites",
        json_body={"email": viewer["email"], "role": "viewer"},
        headers=owner_tokens["headers"],
    )
    accepted = await api.post(
        "/boards/invites/accept",
        json_body={"token": invite.json()["invitation_token"]},
        headers=viewer_tokens["headers"],
    )
    section = await create_section(api, owner_tokens["headers"], board["id"])
    ticket = await create_ticket(api, owner_tokens["headers"], board["id"], section["id"])
    ticket_path = (
        f"/boards/{board['id']}/sections/{section['id']}/tickets/{ticket['id']}"
    )

    read = await api.get(ticket_path, headers=viewer_tokens["headers"])
    create = await api.post(
        f"/boards/{board['id']}/sections/{section['id']}/tickets/",
        json_body={"name": "Forbidden", "description": "Viewer cannot create"},
        headers=viewer_tokens["headers"],
    )
    update = await api.patch(
        ticket_path,
        json_body={"name": "Forbidden"},
        headers=viewer_tokens["headers"],
    )
    archive = await api.delete(ticket_path, headers=viewer_tokens["headers"])
    hard_delete = await api.delete(
        f"{ticket_path}/permanent", headers=viewer_tokens["headers"]
    )

    assert accepted.status_code == status.HTTP_200_OK
    assert read.status_code == status.HTTP_200_OK
    assert create.status_code == status.HTTP_403_FORBIDDEN
    assert update.status_code == status.HTTP_403_FORBIDDEN
    assert archive.status_code == status.HTTP_403_FORBIDDEN
    assert hard_delete.status_code == status.HTTP_403_FORBIDDEN
