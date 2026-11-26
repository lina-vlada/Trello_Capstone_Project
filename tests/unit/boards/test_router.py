from datetime import timedelta
from unittest.mock import AsyncMock, patch
import pytest
from config import settings
from modules.boards import router as boards_router
from modules.boards.schemas import (
    BoardCreate,
    BoardInviteAccept,
    BoardInviteRequest,
    BoardUpdate,
)
from entities.board_user import BoardRole


@pytest.mark.asyncio
async def test_list_user_boards_forwards_user_and_database(boards_db, boards_user):
    boards = [object(), object()]

    with patch.object(
        boards_router, "get_user_boards", new_callable=AsyncMock, return_value=boards
    ) as get_user_boards:
        result = await boards_router.list_user_boards(boards_user, boards_db)

    assert result == boards
    get_user_boards.assert_awaited_once_with(boards_user, boards_db)


@pytest.mark.asyncio
async def test_get_user_board_forwards_board_id_user_and_database(boards_db, boards_user):
    board = object()

    with patch.object(
        boards_router, "get_board", new_callable=AsyncMock, return_value=board
    ) as get_board:
        result = await boards_router.get_user_board(7, boards_user, boards_db)

    assert result is board
    get_board.assert_awaited_once_with(boards_user, boards_db, 7)


@pytest.mark.asyncio
async def test_list_board_section_tickets_forwards_pagination(boards_db, boards_user):
    tickets = [object()]

    with patch.object(
        boards_router, "list_section_tickets", new_callable=AsyncMock, return_value=tickets
    ) as list_tickets:
        result = await boards_router.list_board_section_tickets(
            7, 3, boards_user, boards_db, limit=25, offset=10
        )

    assert result == tickets
    list_tickets.assert_awaited_once_with(boards_user, boards_db, 7, 3, 25, 10)


@pytest.mark.asyncio
async def test_create_user_board_forwards_request(boards_db, boards_user):
    data = BoardCreate(name="Sprint")
    board = object()

    with patch.object(
        boards_router, "create_board", new_callable=AsyncMock, return_value=board
    ) as create_board:
        result = await boards_router.create_user_board(data, boards_user, boards_db)

    assert result is board
    create_board.assert_awaited_once_with(boards_user, boards_db, data)


@pytest.mark.asyncio
async def test_update_user_board_forwards_board_and_request(boards_db, boards_user):
    data = BoardUpdate(name="Updated")
    board = object()

    with patch.object(
        boards_router, "update_board", new_callable=AsyncMock, return_value=board
    ) as update_board:
        result = await boards_router.update_user_board(7, data, boards_user, boards_db)

    assert result is board
    update_board.assert_awaited_once_with(boards_user, boards_db, data, 7)


@pytest.mark.asyncio
async def test_archive_user_board_forwards_board_id(boards_db, boards_user):
    with patch.object(
        boards_router, "soft_delete_board", new_callable=AsyncMock
    ) as soft_delete:
        result = await boards_router.archive_user_board(7, boards_user, boards_db)

    assert result is None
    soft_delete.assert_awaited_once_with(boards_user, boards_db, 7)


@pytest.mark.asyncio
async def test_permanently_delete_user_board_forwards_board_id(boards_db, boards_user):
    with patch.object(
        boards_router, "hard_delete_board", new_callable=AsyncMock
    ) as hard_delete:
        result = await boards_router.permanently_delete_user_board(7, boards_user, boards_db)

    assert result is None
    hard_delete.assert_awaited_once_with(boards_user, boards_db, 7)


@pytest.mark.asyncio
async def test_create_board_invite_returns_token(boards_db, boards_redis, boards_user):
    data = BoardInviteRequest(email="invitee@example.com", role=BoardRole.EDITOR)

    with patch.object(
        boards_router, "invite_user_to_board", new_callable=AsyncMock, return_value="token"
    ) as invite:
        response = await boards_router.create_board_invite(
            7, data, boards_user, boards_db, boards_redis
        )

    assert response == {"invitation_token": "token"}
    invite.assert_awaited_once()
    assert invite.await_args.args[:5] == (boards_user, boards_db, boards_redis, 7, data)
    assert invite.await_args.args[5] == timedelta(
        days=settings.auth_jwt.invite_token_expire_days
    )


@pytest.mark.asyncio
async def test_accept_board_invite_returns_membership_details(boards_db, boards_redis, boards_user):
    membership = type(
        "Membership",
        (),
        {"board_id": 7, "role": BoardRole.EDITOR},
    )()
    data = BoardInviteAccept(token="token")

    with patch.object(
        boards_router, "accept_invitation", new_callable=AsyncMock, return_value=membership
    ) as accept:
        response = await boards_router.accept_board_invite(
            data, boards_user, boards_db, boards_redis
        )

    assert response == {
        "message": "Invitation accepted successfully",
        "board_id": 7,
        "role": BoardRole.EDITOR,
    }
    accept.assert_awaited_once_with(boards_user, boards_db, boards_redis, data)


def test_board_invite_request_rejects_owner_role():
    with pytest.raises(ValueError, match="Invite role must be editor or viewer"):
        BoardInviteRequest(email="owner@example.com", role=BoardRole.OWNER)
