from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from entities.board import Board
from entities.board_user import BoardRole, BoardUser
from entities.section import Section
from entities.ticket import Ticket
from entities.ticket_user import TicketRole, TicketUser
from entities.user import User
from modules.tickets.schemas import TicketCreate, TicketUpdate


async def _require_section_role(db: AsyncSession, user_id: int, board_id: int, section_id: int, allowed_roles: set[BoardRole]) -> Section:
    result = await db.execute(
        select(Section, BoardUser)
        .join(Board, Board.id == Section.board_id)
        .join(BoardUser, BoardUser.board_id == Board.id)
        .where(
            Section.id == section_id,
            Section.board_id == board_id,
            Section.is_archived.is_(False),
            Board.is_archived.is_(False),
            BoardUser.user_id == user_id,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")

    section, membership = row
    if membership.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to perform this action",
        )
    return section


async def _get_ticket(db: AsyncSession, section_id: int, ticket_id: int, include_archived: bool = False) -> Ticket:
    query = (
        select(Ticket)
        .options(selectinload(Ticket.memberships))
        .where(Ticket.id == ticket_id, Ticket.section_id == section_id)
    )
    if not include_archived:
        query = query.where(Ticket.is_archived.is_(False))

    result = await db.execute(query)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


async def _validated_assignee_ids(db: AsyncSession, board_id: int, assignee_ids: list[int]) -> list[int]:
    unique_ids = list(dict.fromkeys(assignee_ids))
    if not unique_ids:
        return []

    result = await db.execute(
        select(BoardUser.user_id).where(
            BoardUser.board_id == board_id,
            BoardUser.user_id.in_(unique_ids),
        )
    )
    board_member_ids = set(result.scalars().all())
    if board_member_ids != set(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="All assignees must be members of the board",
        )
    return unique_ids


async def _get_target_section(db: AsyncSession, board_id: int, section_id: int) -> Section:
    result = await db.execute(
        select(Section).where(
            Section.id == section_id,
            Section.board_id == board_id,
            Section.is_archived.is_(False),
        )
    )
    section = result.scalar_one_or_none()
    if section is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target section not found",
        )
    return section


async def get_ticket(user: User, db: AsyncSession, board_id: int, section_id: int, ticket_id: int) -> Ticket:
    await _require_section_role(db, user.id, board_id, section_id, {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER})
    return await _get_ticket(db, section_id, ticket_id)


async def list_archived_tickets(user: User, db: AsyncSession, board_id: int, section_id: int) -> list[Ticket]:
    await _require_section_role(db, user.id, board_id, section_id, {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER})
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.memberships))
        .where(Ticket.section_id == section_id, Ticket.is_archived.is_(True))
    )
    return list(result.scalars().all())


async def create_ticket(user: User, db: AsyncSession, board_id: int, section_id: int, data: TicketCreate) -> Ticket:
    await _require_section_role(db, user.id, board_id, section_id, {BoardRole.OWNER, BoardRole.EDITOR})
    assignee_ids = await _validated_assignee_ids(db, board_id, data.assignee_ids)

    ticket = Ticket(
        name=data.name,
        description=data.description,
        is_archived=False,
        section_id=section_id,
        memberships=[TicketUser(user_id=user.id, role=TicketRole.CREATOR)],
    )
    creator_ids = {user.id}
    ticket.memberships.extend(
        TicketUser(user_id=assignee_id, role=TicketRole.MEMBER)
        for assignee_id in assignee_ids
        if assignee_id not in creator_ids
    )
    db.add(ticket)
    await db.commit()
    return ticket


async def update_ticket(user: User, db: AsyncSession, board_id: int, section_id: int, ticket_id: int, data: TicketUpdate) -> Ticket:
    await _require_section_role(db, user.id, board_id, section_id, {BoardRole.OWNER, BoardRole.EDITOR})
    ticket = await _get_ticket(db, section_id, ticket_id)
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide at least one field to update",
        )
    if "name" in updates and updates["name"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ticket name cannot be null",
        )
    if "description" in updates and updates["description"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ticket description cannot be null",
        )

    if "assignee_ids" in updates:
        assignee_ids = updates.pop("assignee_ids")
        if assignee_ids is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Assignee IDs cannot be null",
            )
        assignee_ids = await _validated_assignee_ids(db, board_id, assignee_ids)
        creators = [
            membership
            for membership in ticket.memberships
            if membership.role is TicketRole.CREATOR
        ]
        creator_ids = {membership.user_id for membership in creators}
        ticket.memberships = creators + [
            TicketUser(user_id=assignee_id, role=TicketRole.MEMBER)
            for assignee_id in assignee_ids
            if assignee_id not in creator_ids
        ]

    if "section_id" in updates:
        target_section_id = updates.pop("section_id")
        if target_section_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Section ID cannot be null",
            )
        target_section = await _get_target_section(db, board_id, target_section_id)
        ticket.section_id = target_section.id

    for field, value in updates.items():
        setattr(ticket, field, value)

    await db.commit()
    return ticket


async def soft_delete_ticket(user: User, db: AsyncSession, board_id: int, section_id: int, ticket_id: int) -> None:
    await _require_section_role(db, user.id, board_id, section_id, {BoardRole.OWNER, BoardRole.EDITOR})
    ticket = await _get_ticket(db, section_id, ticket_id)
    ticket.is_archived = True
    await db.commit()


async def hard_delete_ticket(user: User, db: AsyncSession, board_id: int, section_id: int, ticket_id: int) -> None:
    await _require_section_role(db, user.id, board_id, section_id, {BoardRole.OWNER})
    ticket = await _get_ticket(db, section_id, ticket_id, include_archived=True)
    if not ticket.is_archived:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archive the ticket first",
        )
    await db.delete(ticket)
    await db.commit()