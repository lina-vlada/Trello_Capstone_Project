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
    invitation = await api.post(
        f"/boards/{board['id']}/invites",
        json_body={"email": member["email"], "role": role},
        headers=owner_tokens["headers"],
    )
    assert invitation.status_code == status.HTTP_201_CREATED
    accepted = await api.post(
        "/boards/invites/accept",
        json_body={"token": invitation.json()["invitation_token"]},
        headers=member_tokens["headers"],
    )
    assert accepted.status_code == status.HTTP_200_OK
    return board


@pytest.mark.asyncio
async def test_section_create_get_list_update_and_validation(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    board = await create_board(api, owner_tokens["headers"])
    base = f"/boards/{board['id']}/sections"

    created = await api.post(
        f"{base}/",
        json_body={"name": "Backlog", "description": "Work to do"},
        headers=owner_tokens["headers"],
    )
    section_id = created.json()["id"]
    listed = await api.get(f"{base}/", headers=owner_tokens["headers"])
    fetched = await api.get(f"{base}/{section_id}", headers=owner_tokens["headers"])
    updated = await api.patch(
        f"{base}/{section_id}",
        json_body={"name": "Ready", "description": None},
        headers=owner_tokens["headers"],
    )
    empty_update = await api.patch(
        f"{base}/{section_id}", json_body={}, headers=owner_tokens["headers"]
    )
    null_name = await api.patch(
        f"{base}/{section_id}",
        json_body={"name": None},
        headers=owner_tokens["headers"],
    )
    invalid_create = await api.post(
        f"{base}/",
        json_body={"name": "", "description": "x" * 301},
        headers=owner_tokens["headers"],
    )

    assert created.status_code == status.HTTP_201_CREATED
    assert created.json()["tickets"] == []
    assert created.json()["is_archived"] is False
    assert listed.status_code == status.HTTP_200_OK
    assert [section["id"] for section in listed.json()] == [section_id]
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["id"] == section_id
    assert updated.status_code == status.HTTP_200_OK
    assert updated.json()["name"] == "Ready"
    assert updated.json()["description"] is None
    assert empty_update.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert null_name.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert invalid_create.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_section_archive_hides_it_restores_it_and_permanent_delete_requires_archive(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    board = await create_board(api, owner_tokens["headers"])
    section = await create_section(api, owner_tokens["headers"], board["id"])
    section_id = section["id"]
    base = f"/boards/{board['id']}/sections"

    premature_delete = await api.delete(
        f"{base}/{section_id}/permanent", headers=owner_tokens["headers"]
    )
    archived = await api.delete(f"{base}/{section_id}", headers=owner_tokens["headers"])
    hidden = await api.get(
        f"{base}/{section_id}", headers=owner_tokens["headers"]
    )
    archived_list = await api.get(f"{base}/archived", headers=owner_tokens["headers"])
    active_list = await api.get(f"{base}/", headers=owner_tokens["headers"])
    restored = await api.patch(
        f"{base}/{section_id}/restore", headers=owner_tokens["headers"]
    )
    duplicate_restore = await api.patch(
        f"{base}/{section_id}/restore", headers=owner_tokens["headers"]
    )
    archived_again = await api.delete(
        f"{base}/{section_id}", headers=owner_tokens["headers"]
    )
    permanent_delete = await api.delete(
        f"{base}/{section_id}/permanent", headers=owner_tokens["headers"]
    )

    assert premature_delete.status_code == status.HTTP_409_CONFLICT
    assert archived.status_code == status.HTTP_204_NO_CONTENT
    assert hidden.status_code == status.HTTP_404_NOT_FOUND
    assert [item["id"] for item in archived_list.json()] == [section_id]
    assert active_list.json() == []
    assert restored.status_code == status.HTTP_200_OK
    assert restored.json()["is_archived"] is False
    assert duplicate_restore.status_code == status.HTTP_409_CONFLICT
    assert archived_again.status_code == status.HTTP_204_NO_CONTENT
    assert permanent_delete.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_archiving_section_archives_its_tickets(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    board = await create_board(api, owner_tokens["headers"])
    section = await create_section(api, owner_tokens["headers"], board["id"])
    ticket = await create_ticket(
        api, owner_tokens["headers"], board["id"], section["id"]
    )

    archived = await api.delete(
        f"/boards/{board['id']}/sections/{section['id']}",
        headers=owner_tokens["headers"],
    )
    archived_sections = await api.get(
        f"/boards/{board['id']}/sections/archived",
        headers=owner_tokens["headers"],
    )
    nested_tickets = archived_sections.json()[0]["tickets"]

    assert archived.status_code == status.HTTP_204_NO_CONTENT
    assert [item["id"] for item in nested_tickets] == [ticket["id"]]
    assert nested_tickets[0]["is_archived"] is True


@pytest.mark.asyncio
async def test_viewer_can_read_sections_but_cannot_mutate_them(api):
    owner = await register_user(api)
    owner_tokens = await login_user(api, owner)
    viewer = await register_user(api)
    viewer_tokens = await login_user(api, viewer)
    board = await _share_board(api, owner_tokens, viewer, viewer_tokens, "viewer")
    section = await create_section(api, owner_tokens["headers"], board["id"])
    base = f"/boards/{board['id']}/sections"

    read_section = await api.get(
        f"{base}/{section['id']}", headers=viewer_tokens["headers"]
    )
    create_section_response = await api.post(
        f"{base}/",
        json_body={"name": "Viewer cannot create"},
        headers=viewer_tokens["headers"],
    )
    update_section = await api.patch(
        f"{base}/{section['id']}",
        json_body={"name": "Viewer cannot update"},
        headers=viewer_tokens["headers"],
    )
    archive_section = await api.delete(
        f"{base}/{section['id']}", headers=viewer_tokens["headers"]
    )
    permanent_delete = await api.delete(
        f"{base}/{section['id']}/permanent", headers=viewer_tokens["headers"]
    )

    assert read_section.status_code == status.HTTP_200_OK
    assert create_section_response.status_code == status.HTTP_403_FORBIDDEN
    assert update_section.status_code == status.HTTP_403_FORBIDDEN
    assert archive_section.status_code == status.HTTP_403_FORBIDDEN
    assert permanent_delete.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_section_routes_hide_nonmember_and_missing_board(api):
    user = await register_user(api)
    tokens = await login_user(api, user)

    missing_board = await api.get(
        "/boards/999999/sections/", headers=tokens["headers"]
    )
    missing_section = await api.get(
        "/boards/999999/sections/1", headers=tokens["headers"]
    )

    assert missing_board.status_code == status.HTTP_404_NOT_FOUND
    assert missing_section.status_code == status.HTTP_404_NOT_FOUND
