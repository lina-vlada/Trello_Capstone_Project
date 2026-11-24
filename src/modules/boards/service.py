from fastapi import status, HTTPException
from modules.auth.dependencies import UserDep
from lib.database.postgres import SessionDep
from modules.boards.schemas import BoardCreate, BoardUpdate, BoardInviteAccept, BoardInviteRequest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from entities.board_user import BoardUser, BoardRole
from entities.ticket import Ticket
from lib.database.redis import RedisDep
from entities.board import Board
from entities.section import Section
from config import settings
from datetime import datetime, timedelta, timezone
from entities.user import User
from typing import List
import uuid
import jwt

async def _get_board_for_user(db: SessionDep,user_id: int,board_id: int,allowed_roles: set[BoardRole],*,include_archived: bool = False,options: list | None = None) -> tuple[Board, BoardUser]:
    stmt = (
        select(Board, BoardUser)
        .join(BoardUser, BoardUser.board_id == Board.id)
        .where(BoardUser.user_id == user_id, Board.id == board_id)
    )
    if not include_archived:
        stmt = stmt.where(Board.is_archived.is_(False))
    if options:
        stmt = stmt.options(*options)

    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Board not found")

    board, membership = row
    if membership.role not in allowed_roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to perform this action",
        )
    return board, membership


    
async def get_user_boards(user: UserDep, db: SessionDep) -> List[Board]:
    result = await db.execute(select(Board)
                              .join(BoardUser, BoardUser.board_id == Board.id)
                              .where(BoardUser.user_id == user.id,
                                     Board.is_archived.is_(False)))
    
    return result.scalars().all()

async def get_board(user: UserDep, db: SessionDep, board_id: int) -> Board:
    board, _ = await _get_board_for_user(
        db, user.id, board_id, {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER},
        options=[selectinload(Board.sections).selectinload(Section.tickets)],
    )
    return board


async def list_section_tickets(user: UserDep, db: SessionDep, board_id: int, section_id: int,limit: int = 50, offset: int = 0) -> list[Ticket]:
    await _get_board_for_user(
        db, user.id, board_id, {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER}
    )
    result = await db.execute(
        select(Ticket)
        .join(Section, Section.id == Ticket.section_id)
        .where(
            Section.id == section_id,
            Section.board_id == board_id,
            Ticket.is_archived.is_(False),
        )
        .order_by(Ticket.id)
        .limit(min(max(limit, 1), 100))
        .offset(max(offset, 0))
    )
    return result.scalars().all()

async def create_board(user: UserDep, db: SessionDep, data: BoardCreate) -> Board:
    board = Board(
        name=data.name,
        description=data.description,
        memberships=[BoardUser(user_id=user.id, role=BoardRole.OWNER)],
    )
    db.add(board)
    await db.commit()
    return board

async def update_board(user: UserDep, db: SessionDep, data: BoardUpdate, board_id: int) -> Board:
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Provide at least one field to update")
    if "name" in updates and updates["name"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Board name cannot be null")

    board, _ = await _get_board_for_user(db, user.id, board_id, {BoardRole.OWNER, BoardRole.EDITOR})

    for field, value in updates.items():
        setattr(board, field, value)

    await db.commit()
    await db.refresh(board)
    return board

async def soft_delete_board(user: UserDep, db: SessionDep, board_id: int) -> None:
    board, _ = await _get_board_for_user(db, user.id, board_id, {BoardRole.OWNER})
    board.is_archived = True
    await db.commit()


async def hard_delete_board(user: UserDep, db: SessionDep, board_id: int) -> None:
    board, _ = await _get_board_for_user(
        db, user.id, board_id, {BoardRole.OWNER}, include_archived=True
    )
    if not board.is_archived:
        raise HTTPException(
            status.HTTP_409_CONFLICT,          
            detail="Archive the board first",  
        )
    await db.delete(board)
    await db.commit()

async def invite_user_to_board(user: UserDep, db:SessionDep, redis: RedisDep, board_id: int, data: BoardInviteRequest, lifetime: timedelta):
    await _get_board_for_user(db, user.id, board_id, {BoardRole.OWNER})
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
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token"
        ) from exc
    if user.email.lower() != email.lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid email address"
        )

    redis_key = f"invite:{board_id}:{jti}"

    token_in_redis = await redis.getdel(redis_key)
    if not token_in_redis:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted or revoked",
        )

    board = await db.scalar(
        select(Board.id).where(Board.id == board_id, Board.is_archived.is_(False))
    )
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Board not found")

    membership = BoardUser(user_id=user.id, board_id=board_id, role=role)
    db.add(membership)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="You are already a member of this board",
        )
    except Exception:
        await db.rollback()
        ttl = max(int(payload["exp"] - datetime.now(timezone.utc).timestamp()), 1)
        await redis.set(redis_key, data.token, ex=ttl)  
        raise

    await db.refresh(membership)
    return membership
    