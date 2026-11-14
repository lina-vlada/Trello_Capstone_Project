from fastapi import status, HTTPException
from modules.auth.dependencies import UserDep
from lib.database.postgres import SessionDep
from modules.boards.schemas import BoardCreate, BoardUpdate, BoardInviteAccept, BoardInviteRequest
from sqlalchemy import select
from entities.board_user import BoardUser, BoardRole
from lib.database.redis import RedisDep
from entities.board import Board
from config import settings
from datetime import datetime, timedelta, timezone
from entities.user import User
from typing import List
import uuid
import jwt

async def _require_board_role(db: SessionDep, user_id: int, board_id: int, allowed_roles: set[BoardRole]) -> tuple[BoardUser,Board]:
    query = await db.execute(select(BoardUser, Board)
                              .join(Board, Board.id == BoardUser.board_id)
                              .where(BoardUser.user_id == user_id, BoardUser.board_id == board_id))
    row = query.first()
    
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Board not found")
    
    membership, board = row
    if membership.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to perform this action",
        )

    return membership, board

    
async def get_user_boards(user: UserDep, db: SessionDep) -> List[Board]:
    result = await db.execute(select(Board)
                              .join(BoardUser, BoardUser.board_id == Board.id)
                              .where(BoardUser.user_id == user.id,
                                     Board.is_archived.is_(False)))
    
    return result.scalars().all()

async def get_board(user: UserDep, db: SessionDep, board_id: int) -> Board:
    _, board = await _require_board_role(db, user.id, board_id,{BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER})

    return board

async def create_board(user: UserDep, db: SessionDep, data: BoardCreate) -> Board:
    board = Board(
        name = data.name,
        description = data.description,
    )
    db.add(board)
    await db.flush()

    db.add(
        BoardUser(
            user_id = user.id,
            board_id = board.id,
            role = BoardRole.OWNER,
        )
    )
    await db.commit()
    await db.refresh(board)

    return board

async def update_board(user: UserDep, db: SessionDep, data: BoardUpdate, board_id: int) -> Board:
    _, board = await _require_board_role(db, user.id, board_id,{BoardRole.OWNER, BoardRole.EDITOR})
    
    updates = data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide at least one field to update",
        )

    for field, value in updates.items():
        setattr(board,field,value)

    await db.commit()
    await db.refresh(board)
    return board

async def soft_delete_board(user: UserDep, db: SessionDep, board_id: int) -> Board:
    _, board = await _require_board_role(db, user.id, board_id,{BoardRole.OWNER})
    board.is_archived = True
    
    await db.commit()
    await db.refresh(board)
    return board

async def hard_delete_board(user: UserDep, db: SessionDep, board_id: int) -> None:
    _, board = await _require_board_role(db, user.id, board_id,{BoardRole.OWNER})

    if not board.is_archived:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail="Archieve the board first"
        )

    await db.delete(board)
    await db.commit()


async def invite_user_to_board(user: UserDep, db:SessionDep, redis: RedisDep, board_id: int, data: BoardInviteRequest, lifetime: timedelta):
    await _require_board_role(db, user.id, board_id, {BoardRole.OWNER})
    user_exists = await db.execute(
        select(BoardUser)
        .join(User, User.id == BoardUser.user_id)
        .where(BoardUser.board_id == board_id, User.email == data.email)
    )
    if user_exists.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this board"
        )
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + lifetime
    payload = {
        "sub": data.email,
        "board_id": board_id,
        "role": data.role.value,
        "jti": jti,
        "exp":  expires_at 
    }
    token = jwt.encode(payload, settings.auth_jwt.private_key, algorithm=settings.auth_jwt.algorithm)

    redis_key = f"invite:{board_id}:{jti}"
    await redis.set(redis_key, token, ex=int(lifetime.total_seconds()))

    return token

async def accept_invitation(user: UserDep, db:SessionDep, redis: RedisDep, data: BoardInviteAccept):
    try:
        payload = jwt.decode(
            data.token,
            settings.auth_jwt.public_key,
            algorithms=[settings.auth_jwt.algorithm],
        )
        email = payload["sub"]
        board_id = int(payload["board_id"])
        role = BoardRole(payload["role"])
        jti = payload["jti"]
        if not isinstance(email, str) or not isinstance(jti, str):
            raise ValueError("Invalid invitation claims")
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token"
        ) from exc
    if user.email != email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid email address"
        )
    redis_key = f"invite:{board_id}:{jti}"
    token_in_redis = await redis.get(redis_key)
    if not token_in_redis:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted or revoked"
        )
    existing = await db.execute(
        select(BoardUser).where(BoardUser.user_id == user.id, BoardUser.board_id == board_id)
    )
    if existing.scalar_one_or_none():
        await redis.delete(redis_key)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a member of this board"
        )
    membership = BoardUser(
        user_id=user.id,
        board_id=board_id,
        role=role,
    )
    
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    await redis.delete(redis_key)

    return membership
    