from unittest.mock import AsyncMock, patch
import pytest
from modules.tickets import router as tickets_router
from modules.tickets.schemas import TicketCreate, TicketUpdate


@pytest.mark.asyncio
async def test_get_section_ticket_forwards_ticket_ids(tickets_db, tickets_user):
    ticket = object()

    with patch.object(
        tickets_router, "get_ticket", new_callable=AsyncMock, return_value=ticket
    ) as get_ticket:
        result = await tickets_router.get_section_ticket(
            9, 4, 5, tickets_user, tickets_db
        )

    assert result is ticket
    get_ticket.assert_awaited_once_with(tickets_user, tickets_db, 9, 4, 5)


@pytest.mark.asyncio
async def test_list_archived_section_tickets_forwards_request(tickets_db, tickets_user):
    tickets = [object()]

    with patch.object(
        tickets_router,
        "list_archived_tickets",
        new_callable=AsyncMock,
        return_value=tickets,
    ) as list_archived:
        result = await tickets_router.list_archived_section_tickets(
            9, 4, tickets_user, tickets_db
        )

    assert result == tickets
    list_archived.assert_awaited_once_with(tickets_user, tickets_db, 9, 4)


@pytest.mark.asyncio
async def test_create_section_ticket_forwards_request(tickets_db, tickets_user):
    data = TicketCreate(name="Fix bug", description="Reproduce and fix")
    ticket = object()

    with patch.object(
        tickets_router, "create_ticket", new_callable=AsyncMock, return_value=ticket
    ) as create_ticket:
        result = await tickets_router.create_section_ticket(
            9, 4, data, tickets_user, tickets_db
        )

    assert result is ticket
    create_ticket.assert_awaited_once_with(tickets_user, tickets_db, 9, 4, data)


@pytest.mark.asyncio
async def test_update_section_ticket_forwards_ticket_and_data(tickets_db, tickets_user):
    data = TicketUpdate(name="Updated")
    ticket = object()

    with patch.object(
        tickets_router, "update_ticket", new_callable=AsyncMock, return_value=ticket
    ) as update_ticket:
        result = await tickets_router.update_section_ticket(
            9, 4, 5, data, tickets_user, tickets_db
        )

    assert result is ticket
    update_ticket.assert_awaited_once_with(tickets_user, tickets_db, 9, 4, 5, data)


@pytest.mark.asyncio
async def test_archive_section_ticket_forwards_ticket_ids(tickets_db, tickets_user):
    with patch.object(
        tickets_router, "soft_delete_ticket", new_callable=AsyncMock
    ) as soft_delete:
        result = await tickets_router.archive_section_ticket(
            9, 4, 5, tickets_user, tickets_db
        )

    assert result is None
    soft_delete.assert_awaited_once_with(tickets_user, tickets_db, 9, 4, 5)


@pytest.mark.asyncio
async def test_permanently_delete_section_ticket_forwards_ticket_ids(
    tickets_db, tickets_user
):
    with patch.object(
        tickets_router, "hard_delete_ticket", new_callable=AsyncMock
    ) as hard_delete:
        result = await tickets_router.permanently_delete_section_ticket(
            9, 4, 5, tickets_user, tickets_db
        )

    assert result is None
    hard_delete.assert_awaited_once_with(tickets_user, tickets_db, 9, 4, 5)
