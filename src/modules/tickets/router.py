from fastapi import APIRouter, status
from lib.database.postgres import SessionDep
from modules.auth.dependencies import UserDep
from modules.tickets.schemas import TicketCreate, TicketResponse, TicketUpdate
from modules.tickets.service import (
    create_ticket,
    get_ticket,
    hard_delete_ticket,
    soft_delete_ticket,
    update_ticket,
)


router = APIRouter(
    prefix="/boards/{board_id}/sections/{section_id}/tickets",
    tags=["Tickets management"],
)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_section_ticket(board_id: int, section_id: int, ticket_id: int, user: UserDep, db: SessionDep):
    return await get_ticket(user, db, board_id, section_id, ticket_id)


@router.post("/", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_section_ticket(board_id: int,section_id: int,data: TicketCreate,user: UserDep,db: SessionDep):
    return await create_ticket(user, db, board_id, section_id, data)


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_section_ticket(board_id: int,section_id: int,ticket_id: int,data: TicketUpdate,user: UserDep,db: SessionDep):
    return await update_ticket(user, db, board_id, section_id, ticket_id, data)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_section_ticket(board_id: int, section_id: int, ticket_id: int, user: UserDep, db: SessionDep) -> None:
    await soft_delete_ticket(user, db, board_id, section_id, ticket_id)


@router.delete("/{ticket_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_section_ticket(board_id: int, section_id: int, ticket_id: int, user: UserDep, db: SessionDep) -> None:
    await hard_delete_ticket(user, db, board_id, section_id, ticket_id)