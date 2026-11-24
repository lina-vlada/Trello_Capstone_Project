import pytest
from fastapi import status
from tests.integration.factories import create_board, create_section, login_user, register_user


@pytest.mark.asyncio
async def test_board_crud_and_membership_scoping(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    outsider = await register_user(api)
    outsider_tokens = await login_user(api, outsider)
    board = await create_board(api, owner_tokens["headers"])
    board_id = board["id"]

    listed = await api.get("/boards/", headers=owner_tokens["headers"])
    details = await api.get(f"/boards/{board_id}", headers=owner_tokens["headers"])
    hidden_list = await api.get("/boards/", headers=outsider_tokens["headers"])
    hidden_details = await api.get(
        f"/boards/{board_id}", headers=outsider_tokens["headers"]
    )

    assert listed.status_code == status.HTTP_200_OK
    assert [item["id"] for item in listed.json()] == [board_id]
    assert details.status_code == status.HTTP_200_OK
    assert details.json()["sections"] == []
    assert hidden_list.json() == []
    assert hidden_details.status_code == status.HTTP_404_NOT_FOUND

    updated = await api.patch(
        f"/boards/{board_id}",
        json_body={"name": "Renamed board", "description": None},
        headers=owner_tokens["headers"],
    )
    assert updated.status_code == status.HTTP_200_OK
    assert updated.json()["name"] == "Renamed board"
    assert updated.json()["description"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": ""},
        {"name": "x" * 101},
        {"name": "Valid", "description": "x" * 301},
    ],
)
@pytest.mark.asyncio
async def test_board_create_and_update_validation(api, payload):
    user = await register_user(api)
    tokens = await login_user(api, user)
    invalid_create = await api.post(
        "/boards/", json_body=payload, headers=tokens["headers"]
    )
    board = await create_board(api, tokens["headers"])
    invalid_update = await api.patch(
        f"/boards/{board['id']}", json_body=payload, headers=tokens["headers"]
    )

    assert invalid_create.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_update.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_board_invites_are_role_limited_and_single_use(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    invitee = await register_user(api)
    invitee_tokens = await login_user(api, invitee)
    wrong_user = await register_user(api)
    wrong_user_tokens = await login_user(api, wrong_user)
    board = await create_board(api, owner_tokens["headers"])
    board_id = board["id"]

    owner_role_invite = await api.post(
        f"/boards/{board_id}/invites",
        json_body={"email": invitee["email"], "role": "owner"},
        headers=owner_tokens["headers"],
    )
    invite = await api.post(
        f"/boards/{board_id}/invites",
        json_body={"email": invitee["email"], "role": "editor"},
        headers=owner_tokens["headers"],
    )
    assert owner_role_invite.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invite.status_code == status.HTTP_201_CREATED
    token = invite.json()["invitation_token"]

    wrong_email = await api.post(
        "/boards/invites/accept",
        json_body={"token": token},
        headers=wrong_user_tokens["headers"],
    )
    accepted = await api.post(
        "/boards/invites/accept",
        json_body={"token": token},
        headers=invitee_tokens["headers"],
    )
    replayed = await api.post(
        "/boards/invites/accept",
        json_body={"token": token},
        headers=invitee_tokens["headers"],
    )

    assert wrong_email.status_code == status.HTTP_404_NOT_FOUND
    assert accepted.status_code == status.HTTP_200_OK
    assert accepted.json()["board_id"] == board_id
    assert accepted.json()["role"] == "editor"
    assert replayed.status_code == status.HTTP_400_BAD_REQUEST

    editor_cannot_invite = await api.post(
        f"/boards/{board_id}/invites",
        json_body={"email": wrong_user["email"], "role": "viewer"},
        headers=invitee_tokens["headers"],
    )
    assert editor_cannot_invite.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_editor_and_viewer_permissions(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    editor = await register_user(api)
    editor_tokens = await login_user(api, editor)
    viewer = await register_user(api)
    viewer_tokens = await login_user(api, viewer)
    board = await create_board(api, owner_tokens["headers"])
    board_id = board["id"]

    for user, role in ((editor, "editor"), (viewer, "viewer")):
        invitation = await api.post(
            f"/boards/{board_id}/invites",
            json_body={"email": user["email"], "role": role},
            headers=owner_tokens["headers"],
        )
        assert invitation.status_code == status.HTTP_201_CREATED
        accepted = await api.post(
            "/boards/invites/accept",
            json_body={"token": invitation.json()["invitation_token"]},
            headers=(editor_tokens if role == "editor" else viewer_tokens)["headers"],
        )
        assert accepted.status_code == status.HTTP_200_OK

    editor_update = await api.patch(
        f"/boards/{board_id}",
        json_body={"name": "Editor update"},
        headers=editor_tokens["headers"],
    )
    viewer_update = await api.patch(
        f"/boards/{board_id}",
        json_body={"name": "Forbidden update"},
        headers=viewer_tokens["headers"],
    )
    editor_archive = await api.delete(
        f"/boards/{board_id}", headers=editor_tokens["headers"]
    )
    viewer_archive = await api.delete(
        f"/boards/{board_id}", headers=viewer_tokens["headers"]
    )

    assert editor_update.status_code == status.HTTP_200_OK
    assert viewer_update.status_code == status.HTTP_403_FORBIDDEN
    assert editor_archive.status_code == status.HTTP_403_FORBIDDEN
    assert viewer_archive.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_board_archive_must_precede_permanent_delete(api):
    owner = await register_user(api)
    tokens = await login_user(api, owner)
    board = await create_board(api, tokens["headers"])
    board_id = board["id"]

    premature_delete = await api.delete(
        f"/boards/{board_id}/permanent", headers=tokens["headers"]
    )
    archived = await api.delete(f"/boards/{board_id}", headers=tokens["headers"])
    unavailable_details = await api.get(
        f"/boards/{board_id}", headers=tokens["headers"]
    )
    permanent_delete = await api.delete(
        f"/boards/{board_id}/permanent", headers=tokens["headers"]
    )

    assert premature_delete.status_code == status.HTTP_409_CONFLICT
    assert archived.status_code == status.HTTP_204_NO_CONTENT
    assert unavailable_details.status_code == status.HTTP_404_NOT_FOUND
    assert permanent_delete.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_archived_board_invitation_is_not_accepted(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    invitee = await register_user(api)
    invitee_tokens = await login_user(api, invitee)
    board = await create_board(api, owner_tokens["headers"])
    invite = await api.post(
        f"/boards/{board['id']}/invites",
        json_body={"email": invitee["email"], "role": "viewer"},
        headers=owner_tokens["headers"],
    )
    archived = await api.delete(
        f"/boards/{board['id']}", headers=owner_tokens["headers"]
    )

    accepted = await api.post(
        "/boards/invites/accept",
        json_body={"token": invite.json()["invitation_token"]},
        headers=invitee_tokens["headers"],
    )

    assert archived.status_code == status.HTTP_204_NO_CONTENT
    assert accepted.status_code == status.HTTP_404_NOT_FOUND

    permanently_deleted = await api.delete(
        f"/boards/{board['id']}/permanent", headers=owner_tokens["headers"]
    )
    assert permanently_deleted.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_board_section_ticket_listing_validates_parent_ids(api):
    owner = await register_user(api)
    tokens = await login_user(api, owner)
    board = await create_board(api, tokens["headers"])
    section = await create_section(api, tokens["headers"], board["id"])
    wrong_board = await api.get(
        f"/boards/{board['id']}/sections/999/tickets", headers=tokens["headers"]
    )
    invalid_section_id = await api.get(
        f"/boards/{board['id']}/sections/not-an-int/tickets",
        headers=tokens["headers"],
    )

    assert wrong_board.status_code == status.HTTP_200_OK
    assert wrong_board.json() == []
    assert section["board_id"] == board["id"]
    assert invalid_section_id.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
