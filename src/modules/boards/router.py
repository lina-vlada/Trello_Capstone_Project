from datetime import timedelta
from fastapi import APIRouter, status
from config import settings
from lib.database.postgres import SessionDep
from lib.database.redis import RedisDep
from modules.auth.dependencies import UserDep
from modules.boards.schemas import (
    BoardCreate,
    BoardInviteAccept,
    BoardInviteRequest,
    BoardResponse,
    BoardUpdate,
)
from modules.boards.service import (
    accept_invitation,
    create_board,
    get_board,
    get_user_boards,
    hard_delete_board,
    invite_user_to_board,
    soft_delete_board,
    update_board,
)

router = APIRouter(prefix="/boards", tags=["Boards management"])


@router.get("/", response_model=list[BoardResponse])
async def list_user_boards(user: UserDep, db: SessionDep):
    return await get_user_boards(user, db)


@router.get("/{board_id}", response_model=BoardResponse)
async def get_user_board(board_id: int, user: UserDep, db: SessionDep):
    return await get_board(user, db, board_id)


@router.post("/", response_model=BoardResponse, status_code=status.HTTP_201_CREATED)
async def create_user_board(data: BoardCreate, user: UserDep, db: SessionDep):
    return await create_board(user, db, data)


@router.patch("/{board_id}", response_model=BoardResponse)
async def update_user_board(board_id: int, data: BoardUpdate, user: UserDep, db: SessionDep):
    return await update_board(user, db, data, board_id)


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_user_board(board_id: int, user: UserDep, db: SessionDep) -> None:
    await soft_delete_board(user, db, board_id)


@router.delete("/{board_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_user_board(board_id: int, user: UserDep, db: SessionDep) -> None:
    await hard_delete_board(user, db, board_id)


@router.post("/{board_id}/invites", status_code=status.HTTP_201_CREATED)
async def create_board_invite(board_id: int, data: BoardInviteRequest, user: UserDep, db: SessionDep, redis: RedisDep):
    token = await invite_user_to_board(user, db, redis, board_id, data, timedelta(days=settings.auth_jwt.invite_token_expire_days))
    return {"invitation_token": token}


@router.post("/invites/accept")
async def accept_board_invite(data: BoardInviteAccept, user: UserDep, db: SessionDep, redis: RedisDep):
    membership = await accept_invitation(user, db, redis, data)
    return {
        "message": "Invitation accepted successfully",
        "board_id": membership.board_id,
        "role": membership.role,
    }
