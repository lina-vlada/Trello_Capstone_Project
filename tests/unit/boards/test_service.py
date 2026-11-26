from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import jwt
import pytest
from fastapi import status
from pydantic import ValidationError
from fastapi.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from entities.board import Board
from entities.board_user import BoardRole, BoardUser
from modules.boards import service
from modules.boards.schemas import (
    BoardCreate,
    BoardDetailResponse,
    BoardInviteAccept,
    BoardInviteRequest,
    BoardResponse,
    BoardUpdate,
)


def _db_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalars.return_value.all.return_value = value
    return result


def _user(user_id=1, email="member@example.com"):
    return SimpleNamespace(id=user_id, email=email)


def _mock_invitation_decode(monkeypatch, payload):
    monkeypatch.setattr(service.jwt, "decode", MagicMock(return_value=payload))
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(auth_jwt=SimpleNamespace(public_key="public-key", algorithm="RS256")),
    )


@pytest.mark.asyncio
async def test_get_board_for_user_returns_membership_for_allowed_role(boards_db):
    membership = SimpleNamespace(role=BoardRole.EDITOR)
    board = SimpleNamespace(id=2)
    result = MagicMock()
    result.one_or_none.return_value = (board, membership)
    boards_db.execute.return_value = result

    returned_board, returned_membership = await service._get_board_for_user(
        boards_db, 1, 2, {BoardRole.OWNER, BoardRole.EDITOR}
    )

    assert returned_board is board
    assert returned_membership is membership
    boards_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_board_for_user_rejects_non_member(boards_db):
    result = MagicMock()
    result.one_or_none.return_value = None
    boards_db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await service._get_board_for_user(boards_db, 1, 2, {BoardRole.OWNER})

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Board not found"


@pytest.mark.asyncio
async def test_get_board_for_user_rejects_insufficient_role(boards_db):
    membership = SimpleNamespace(role=BoardRole.VIEWER)
    result = MagicMock()
    result.one_or_none.return_value = (SimpleNamespace(id=2), membership)
    boards_db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await service._get_board_for_user(boards_db, 1, 2, {BoardRole.OWNER})

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_board_for_user_can_include_archived_boards(boards_db):
    board = SimpleNamespace(id=2, is_archived=True)
    membership = SimpleNamespace(role=BoardRole.OWNER)
    result = MagicMock()
    result.one_or_none.return_value = (board, membership)
    boards_db.execute.return_value = result

    returned_board, _ = await service._get_board_for_user(
        boards_db, 1, 2, {BoardRole.OWNER}, include_archived=True
    )

    assert returned_board is board
    where_clause = boards_db.execute.await_args.args[0].whereclause
    assert "boards.is_archived" not in str(where_clause)


@pytest.mark.asyncio
async def test_get_board_for_user_applies_requested_query_options(boards_db):
    result = MagicMock()
    result.one_or_none.return_value = (
        SimpleNamespace(id=2),
        SimpleNamespace(role=BoardRole.OWNER),
    )
    boards_db.execute.return_value = result
    options = [selectinload(Board.sections)]

    await service._get_board_for_user(
        boards_db, 1, 2, {BoardRole.OWNER}, options=options
    )

    statement = boards_db.execute.await_args.args[0]
    assert statement._with_options == tuple(options)


@pytest.mark.asyncio
async def test_get_user_boards_returns_query_results(boards_db, boards_user):
    boards = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    boards_db.execute.return_value = _db_result(boards)

    result = await service.get_user_boards(boards_user, boards_db)

    assert result == boards
    boards_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_board_checks_membership_and_returns_board(monkeypatch, boards_db, boards_user):
    board = SimpleNamespace(id=2)
    get_board_for_user = AsyncMock(return_value=(board, SimpleNamespace(role=BoardRole.VIEWER)))
    monkeypatch.setattr(service, "_get_board_for_user", get_board_for_user)

    result = await service.get_board(boards_user, boards_db, 2)

    assert result is board
    get_board_for_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_section_tickets_clamps_limit_and_offset(monkeypatch, boards_db, boards_user):
    tickets = [SimpleNamespace(id=1)]
    boards_db.execute.return_value = _db_result(tickets)
    get_board_for_user = AsyncMock(return_value=(SimpleNamespace(id=2), None))
    monkeypatch.setattr(service, "_get_board_for_user", get_board_for_user)

    result = await service.list_section_tickets(
        boards_user, boards_db, board_id=2, section_id=3, limit=500, offset=-4
    )

    statement = boards_db.execute.await_args.args[0]
    assert result == tickets
    assert statement._limit_clause.value == 100
    assert statement._offset_clause.value == 0
    get_board_for_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_section_tickets_enforces_minimum_limit(monkeypatch, boards_db, boards_user):
    boards_db.execute.return_value = _db_result([])
    monkeypatch.setattr(
        service,
        "_get_board_for_user",
        AsyncMock(return_value=(SimpleNamespace(id=2), None)),
    )

    await service.list_section_tickets(
        boards_user, boards_db, board_id=2, section_id=3, limit=0
    )

    assert boards_db.execute.await_args.args[0]._limit_clause.value == 1


@pytest.mark.asyncio
async def test_create_board_creates_board_and_owner_membership(boards_db, boards_user):

    board = await service.create_board(
        boards_user,
        boards_db,
        BoardCreate(name="Sprint", description="Sprint planning"),
    )

    membership = board.memberships[0]
    assert board.name == "Sprint"
    assert board.description == "Sprint planning"
    assert isinstance(membership, BoardUser)
    assert membership.user_id == 1
    assert membership.role is BoardRole.OWNER
    boards_db.commit.assert_awaited_once()
    boards_db.add.assert_called_once_with(board)


@pytest.mark.asyncio
async def test_update_board_applies_only_provided_fields(monkeypatch, boards_db, boards_user):
    board = SimpleNamespace(name="Old", description="Keep")
    get_board_for_user = AsyncMock(return_value=(board, SimpleNamespace(role=BoardRole.EDITOR)))
    monkeypatch.setattr(service, "_get_board_for_user", get_board_for_user)

    result = await service.update_board(
        boards_user, boards_db, BoardUpdate(name="New"), 2
    )

    assert result is board
    assert board.name == "New"
    assert board.description == "Keep"
    get_board_for_user.assert_awaited_once()
    boards_db.commit.assert_awaited_once()
    boards_db.refresh.assert_awaited_once_with(board)


def test_board_update_rejects_empty_payload():
    with pytest.raises(ValidationError):
        BoardUpdate()


def test_board_update_rejects_null_name():
    with pytest.raises(ValidationError):
        BoardUpdate(name=None)


def test_board_update_rejects_name_over_maximum():
    with pytest.raises(ValidationError):
        BoardUpdate(name="x" * 101)


@pytest.mark.asyncio
async def test_update_board_rejects_empty_update(boards_db, boards_user):
    with pytest.raises(HTTPException) as exc_info:
        await service.update_board(boards_user, boards_db, BoardUpdate.model_construct(), 2)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    boards_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_board_rejects_null_name(boards_db, boards_user):
    with pytest.raises(HTTPException) as exc_info:
        await service.update_board(
            boards_user, boards_db, BoardUpdate.model_construct(name=None), 2
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    boards_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_board_can_clear_description(monkeypatch, boards_db, boards_user):
    board = SimpleNamespace(name="Sprint", description="Old description")
    monkeypatch.setattr(
        service,
        "_get_board_for_user",
        AsyncMock(return_value=(board, SimpleNamespace(role=BoardRole.OWNER))),
    )

    result = await service.update_board(
        boards_user, boards_db, BoardUpdate(description=None), 2
    )

    assert result.description is None
    boards_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_soft_delete_archives_board(monkeypatch, boards_db, boards_user):
    board = SimpleNamespace(is_archived=False)
    get_board_for_user = AsyncMock(return_value=(board, SimpleNamespace(role=BoardRole.OWNER)))
    monkeypatch.setattr(service, "_get_board_for_user", get_board_for_user)

    result = await service.soft_delete_board(boards_user, boards_db, 2)

    assert result is None
    assert board.is_archived is True
    get_board_for_user.assert_awaited_once()
    boards_db.commit.assert_awaited_once()
    boards_db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_hard_delete_requires_board_to_be_archived(monkeypatch, boards_db, boards_user):
    board = SimpleNamespace(is_archived=False)
    monkeypatch.setattr(service, "_get_board_for_user", AsyncMock(return_value=(board, SimpleNamespace(role=BoardRole.OWNER))))

    with pytest.raises(HTTPException) as exc_info:
        await service.hard_delete_board(boards_user, boards_db, 2)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    boards_db.delete.assert_not_awaited()
    boards_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_hard_delete_removes_archived_board(monkeypatch, boards_db, boards_user):
    board = SimpleNamespace(is_archived=True)
    monkeypatch.setattr(service, "_get_board_for_user", AsyncMock(return_value=(board, SimpleNamespace(role=BoardRole.OWNER))))

    result = await service.hard_delete_board(boards_user, boards_db, 2)

    assert result is None
    boards_db.delete.assert_awaited_once_with(board)
    boards_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_hard_delete_allows_archived_board_only(monkeypatch, boards_db, boards_user):
    board = SimpleNamespace(is_archived=True)
    get_board_for_user = AsyncMock(return_value=(board, SimpleNamespace(role=BoardRole.OWNER)))
    monkeypatch.setattr(service, "_get_board_for_user", get_board_for_user)

    await service.hard_delete_board(boards_user, boards_db, 2)

    assert get_board_for_user.await_args.kwargs["include_archived"] is True


@pytest.mark.asyncio
async def test_invite_user_creates_token_and_stores_it(
    monkeypatch, boards_db, boards_redis, boards_user
):
    encode = MagicMock(return_value="signed-invitation")
    monkeypatch.setattr(
        service,
        "_get_board_for_user",
        AsyncMock(return_value=(SimpleNamespace(), SimpleNamespace(role=BoardRole.OWNER))),
    )
    monkeypatch.setattr(service.jwt, "encode", encode)
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(auth_jwt=SimpleNamespace(private_key="private-key", algorithm="RS256")),
    )
    invitation = BoardInviteRequest(email="invitee@example.com", role=BoardRole.EDITOR)

    token = await service.invite_user_to_board(
        boards_user, boards_db, boards_redis, 7, invitation, timedelta(hours=2)
    )

    assert token == "signed-invitation"
    payload = encode.call_args.args[0]
    assert payload["sub"] == "invitee@example.com"
    assert payload["board_id"] == 7
    assert payload["role"] == BoardRole.EDITOR.value
    boards_redis.set.assert_awaited_once()
    key, stored_token = boards_redis.set.call_args.args
    assert key == f"invite:7:{payload['jti']}"
    assert stored_token == token
    assert boards_redis.set.call_args.kwargs["ex"] == 7200





@pytest.mark.asyncio
async def test_accept_invitation_adds_membership_and_consumes_token(
    monkeypatch, boards_db, boards_redis, boards_user
):
    payload = {
        "sub": "member@example.com",
        "board_id": 7,
        "role": BoardRole.EDITOR.value,
        "jti": "invite-id",
        "exp": 4102444800,
    }
    boards_db.scalar.return_value = 7
    boards_redis.getdel.return_value = "signed-invitation"
    _mock_invitation_decode(monkeypatch, payload)

    membership = await service.accept_invitation(
        boards_user, boards_db, boards_redis, BoardInviteAccept(token="signed-invitation")
    )

    assert membership.user_id == 1
    assert membership.board_id == 7
    assert membership.role is BoardRole.EDITOR
    boards_db.add.assert_called_once_with(membership)
    boards_db.commit.assert_awaited_once()
    boards_db.refresh.assert_awaited_once_with(membership)
    boards_redis.getdel.assert_awaited_once_with("invite:7:invite-id")


@pytest.mark.asyncio
async def test_accept_invitation_rejects_invalid_token(monkeypatch, boards_db, boards_redis):
    decode = MagicMock(side_effect=jwt.InvalidTokenError)
    monkeypatch.setattr(service.jwt, "decode", decode)
    monkeypatch.setattr(
        service,
        "settings",
        SimpleNamespace(auth_jwt=SimpleNamespace(public_key="public-key", algorithm="RS256")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.accept_invitation(
            _user(), boards_db, boards_redis, BoardInviteAccept(token="invalid")
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Invalid or expired invitation token"


@pytest.mark.asyncio
async def test_accept_invitation_rejects_different_email(monkeypatch, boards_db, boards_redis):
    payload = {
        "sub": "other@example.com",
        "board_id": 7,
        "role": BoardRole.VIEWER.value,
        "jti": "invite-id",
    }
    _mock_invitation_decode(monkeypatch, payload)

    with pytest.raises(HTTPException) as exc_info:
        await service.accept_invitation(
            _user(), boards_db, boards_redis, BoardInviteAccept(token="signed-invitation")
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    boards_redis.getdel.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_invitation_rejects_consumed_token(monkeypatch, boards_db, boards_redis):
    payload = {
        "sub": "member@example.com",
        "board_id": 7,
        "role": BoardRole.VIEWER.value,
        "jti": "invite-id",
    }
    boards_redis.getdel.return_value = None
    _mock_invitation_decode(monkeypatch, payload)

    with pytest.raises(HTTPException) as exc_info:
        await service.accept_invitation(
            _user(), boards_db, boards_redis, BoardInviteAccept(token="signed-invitation")
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "Invitation has already been accepted or revoked"


@pytest.mark.parametrize(
    "payload",
    [
        {"board_id": 7, "role": BoardRole.VIEWER.value, "jti": "invite-id"},
        {"sub": "member@example.com", "board_id": "bad", "role": "viewer", "jti": "invite-id"},
        {"sub": "member@example.com", "board_id": 7, "role": "invalid", "jti": "invite-id"},
    ],
)
@pytest.mark.asyncio
async def test_accept_invitation_rejects_invalid_claims(
    monkeypatch, boards_db, boards_redis, payload
):
    _mock_invitation_decode(monkeypatch, payload)

    with pytest.raises(HTTPException) as exc_info:
        await service.accept_invitation(
            _user(), boards_db, boards_redis, BoardInviteAccept(token="bad-claims")
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    boards_redis.getdel.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_invitation_rejects_missing_board(monkeypatch, boards_db, boards_redis):
    payload = {
        "sub": "member@example.com",
        "board_id": 7,
        "role": BoardRole.VIEWER.value,
        "jti": "invite-id",
    }
    _mock_invitation_decode(monkeypatch, payload)
    boards_redis.getdel.return_value = "signed-invitation"
    boards_db.scalar.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await service.accept_invitation(
            _user(), boards_db, boards_redis, BoardInviteAccept(token="signed-invitation")
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Board not found"
    boards_redis.getdel.assert_awaited_once_with("invite:7:invite-id")
    boards_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_accept_invitation_rolls_back_duplicate_membership(
    monkeypatch, boards_db, boards_redis
):
    payload = {
        "sub": "member@example.com",
        "board_id": 7,
        "role": BoardRole.VIEWER.value,
        "jti": "invite-id",
    }
    _mock_invitation_decode(monkeypatch, payload)
    boards_redis.getdel.return_value = "signed-invitation"
    boards_db.scalar.return_value = 7
    boards_db.commit.side_effect = IntegrityError("INSERT", {}, Exception("duplicate"))

    with pytest.raises(HTTPException) as exc_info:
        await service.accept_invitation(
            _user(), boards_db, boards_redis, BoardInviteAccept(token="signed-invitation")
        )

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "You are already a member of this board"
    boards_db.rollback.assert_awaited_once()
    boards_db.refresh.assert_not_awaited()
    boards_redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_invitation_restores_token_after_unexpected_commit_error(
    monkeypatch, boards_db, boards_redis
):
    expires_at = int(datetime.now(timezone.utc).timestamp()) + 600
    payload = {
        "sub": "member@example.com",
        "board_id": 7,
        "role": BoardRole.VIEWER.value,
        "jti": "invite-id",
        "exp": expires_at,
    }
    _mock_invitation_decode(monkeypatch, payload)
    boards_redis.getdel.return_value = "signed-invitation"
    boards_db.scalar.return_value = 7
    boards_db.commit.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.accept_invitation(
            _user(), boards_db, boards_redis, BoardInviteAccept(token="signed-invitation")
        )

    boards_db.rollback.assert_awaited_once()
    boards_redis.set.assert_awaited_once()
    key, token = boards_redis.set.await_args.args
    assert key == "invite:7:invite-id"
    assert token == "signed-invitation"
    assert 1 <= boards_redis.set.await_args.kwargs["ex"] <= 600


def test_board_invite_request_normalizes_email():
    invitation = BoardInviteRequest(email="  INVITEE@Example.COM  ")

    assert invitation.email == "invitee@example.com"
    assert invitation.role is BoardRole.VIEWER


def test_board_response_reads_attributes_from_model():
    board = SimpleNamespace(
        id=5,
        name="Sprint",
        description="Planning",
        is_archived=False,
    )

    response = BoardResponse.model_validate(board)

    assert response.model_dump() == {
        "id": 5,
        "name": "Sprint",
        "description": "Planning",
        "is_archived": False,
    }


def test_board_detail_response_includes_existing_section_and_ticket_response_shape():
    board = SimpleNamespace(
        id=5,
        name="Sprint",
        description="Planning",
        is_archived=False,
        sections=[
            SimpleNamespace(
                id=3,
                name="To do",
                description=None,
                is_archived=False,
                board_id=5,
                tickets=[],
            )
        ],
    )

    response = BoardDetailResponse.model_validate(board)

    assert response.sections[0].model_dump() == {
        "id": 3,
        "name": "To do",
        "description": None,
        "is_archived": False,
        "board_id": 5,
        "tickets": [],
    }