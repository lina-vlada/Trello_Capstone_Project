from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import status
from fastapi.exceptions import HTTPException
from pydantic import ValidationError
from entities.ticket import Ticket
from entities.ticket_user import TicketRole
from modules.tickets import service
from modules.tickets.schemas import TicketCreate, TicketResponse, TicketUpdate


def _result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalars.return_value.all.return_value = value
    return result


@pytest.mark.asyncio
async def test_require_section_role_returns_section_for_allowed_role(tickets_db):
    section = SimpleNamespace(id=4)
    membership = SimpleNamespace(role=service.BoardRole.EDITOR)
    result = MagicMock()
    result.first.return_value = (section, membership)
    tickets_db.execute.return_value = result

    returned = await service._require_section_role(
        tickets_db, 1, 9, 4, {service.BoardRole.OWNER, service.BoardRole.EDITOR}
    )

    assert returned is section
    tickets_db.execute.assert_awaited_once()


@pytest.mark.parametrize("row", [None])
@pytest.mark.asyncio
async def test_require_section_role_rejects_missing_or_archived_section(tickets_db, row):
    result = MagicMock()
    result.first.return_value = row
    tickets_db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await service._require_section_role(
            tickets_db, 1, 9, 4, {service.BoardRole.OWNER}
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Section not found"


@pytest.mark.asyncio
async def test_require_section_role_rejects_insufficient_board_role(tickets_db):
    result = MagicMock()
    result.first.return_value = (
        SimpleNamespace(id=4),
        SimpleNamespace(role=service.BoardRole.VIEWER),
    )
    tickets_db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await service._require_section_role(
            tickets_db, 1, 9, 4, {service.BoardRole.OWNER, service.BoardRole.EDITOR}
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_ticket_returns_ticket_in_matching_section(tickets_db):
    ticket = SimpleNamespace(id=5, section_id=4, is_archived=False)
    tickets_db.execute.return_value = _result(ticket)

    result = await service._get_ticket(tickets_db, 4, 5)

    assert result is ticket
    query = tickets_db.execute.await_args.args[0]
    assert "tickets.is_archived" in str(query.whereclause)


@pytest.mark.asyncio
async def test_get_ticket_can_include_archived_ticket(tickets_db):
    ticket = SimpleNamespace(id=5, section_id=4, is_archived=True)
    tickets_db.execute.return_value = _result(ticket)

    result = await service._get_ticket(tickets_db, 4, 5, include_archived=True)

    assert result is ticket
    assert "tickets.is_archived" not in str(
        tickets_db.execute.await_args.args[0].whereclause
    )


@pytest.mark.asyncio
async def test_get_ticket_raises_not_found_for_missing_ticket(tickets_db):
    tickets_db.execute.return_value = _result(None)

    with pytest.raises(HTTPException) as exc_info:
        await service._get_ticket(tickets_db, 4, 5)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Ticket not found"


@pytest.mark.asyncio
async def test_validated_assignee_ids_deduplicates_board_members(tickets_db):
    result = MagicMock()
    result.scalars.return_value.all.return_value = [1, 2]
    tickets_db.execute.return_value = result

    assignees = await service._validated_assignee_ids(tickets_db, 9, [1, 2, 1])

    assert assignees == [1, 2]
    query = tickets_db.execute.await_args.args[0]
    assert "IN (__[POSTCOMPILE_user_id_1])" in str(query.whereclause)


@pytest.mark.asyncio
async def test_validated_assignee_ids_returns_empty_without_query(tickets_db):
    result = await service._validated_assignee_ids(tickets_db, 9, [])

    assert result == []
    tickets_db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_target_section_returns_active_section(tickets_db):
    section = SimpleNamespace(id=8, board_id=9, is_archived=False)
    tickets_db.execute.return_value = _result(section)

    result = await service._get_target_section(tickets_db, 9, 8)

    assert result is section
    assert "sections.is_archived" in str(
        tickets_db.execute.await_args.args[0].whereclause
    )


@pytest.mark.asyncio
async def test_get_target_section_rejects_missing_or_archived_section(tickets_db):
    tickets_db.execute.return_value = _result(None)

    with pytest.raises(HTTPException) as exc_info:
        await service._get_target_section(tickets_db, 9, 8)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Target section not found"


@pytest.mark.asyncio
async def test_create_ticket_adds_creator_and_multiple_assignees(
    monkeypatch, tickets_db, tickets_user
):
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    monkeypatch.setattr(
        service, "_validated_assignee_ids", AsyncMock(return_value=[2, 3, 1])
    )

    ticket = await service.create_ticket(
        tickets_user,
        tickets_db,
        9,
        4,
        TicketCreate(name="Fix bug", description="Reproduce and fix"),
    )

    assert isinstance(ticket, Ticket)
    assert [(membership.user_id, membership.role) for membership in ticket.memberships] == [
        (1, TicketRole.CREATOR),
        (2, TicketRole.MEMBER),
        (3, TicketRole.MEMBER),
    ]
    tickets_db.add.assert_called_once_with(ticket)
    tickets_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_ticket_omits_creator_from_assignee_memberships(
    monkeypatch, tickets_db, tickets_user
):
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    validated_assignees = AsyncMock(return_value=[1])
    monkeypatch.setattr(service, "_validated_assignee_ids", validated_assignees)

    ticket = await service.create_ticket(
        tickets_user,
        tickets_db,
        9,
        4,
        TicketCreate(name="Fix bug", description="Reproduce and fix", assignee_ids=[1]),
    )

    assert [(membership.user_id, membership.role) for membership in ticket.memberships] == [
        (1, TicketRole.CREATOR)
    ]
    validated_assignees.assert_awaited_once_with(tickets_db, 9, [1])


@pytest.mark.asyncio
async def test_get_ticket_checks_section_access_and_returns_active_ticket(
    monkeypatch, tickets_db, tickets_user
):
    ticket = SimpleNamespace(id=5)
    require_role = AsyncMock()
    get_ticket = AsyncMock(return_value=ticket)
    monkeypatch.setattr(service, "_require_section_role", require_role)
    monkeypatch.setattr(service, "_get_ticket", get_ticket)

    result = await service.get_ticket(tickets_user, tickets_db, 9, 4, 5)

    assert result is ticket
    require_role.assert_awaited_once_with(
        tickets_db,
        1,
        9,
        4,
        {service.BoardRole.OWNER, service.BoardRole.EDITOR, service.BoardRole.VIEWER},
    )
    get_ticket.assert_awaited_once_with(tickets_db, 4, 5)


@pytest.mark.asyncio
async def test_update_ticket_replaces_assignees_and_preserves_creator(
    monkeypatch, tickets_db, tickets_user
):
    ticket = Ticket(
        id=5,
        name="Fix bug",
        description="Reproduce and fix",
        section_id=4,
        memberships=[
            service.TicketUser(user_id=1, role=TicketRole.CREATOR),
            service.TicketUser(user_id=2, role=TicketRole.MEMBER),
        ],
    )
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    monkeypatch.setattr(service, "_get_ticket", AsyncMock(return_value=ticket))
    monkeypatch.setattr(
        service, "_validated_assignee_ids", AsyncMock(return_value=[3, 4])
    )

    result = await service.update_ticket(
        tickets_user, tickets_db, 9, 4, 5, TicketUpdate(assignee_ids=[3, 4])
    )

    assert result is ticket
    assert [(membership.user_id, membership.role) for membership in ticket.memberships] == [
        (1, TicketRole.CREATOR),
        (3, TicketRole.MEMBER),
        (4, TicketRole.MEMBER),
    ]
    tickets_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_ticket_can_move_to_another_active_section(
    monkeypatch, tickets_db, tickets_user
):
    ticket = Ticket(
        id=5,
        name="Fix bug",
        description="Reproduce and fix",
        section_id=4,
        memberships=[
            service.TicketUser(user_id=1, role=TicketRole.CREATOR),
            service.TicketUser(user_id=2, role=TicketRole.MEMBER),
        ],
    )
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    monkeypatch.setattr(service, "_get_ticket", AsyncMock(return_value=ticket))
    monkeypatch.setattr(
        service,
        "_get_target_section",
        AsyncMock(return_value=SimpleNamespace(id=8, board_id=9, is_archived=False)),
    )

    result = await service.update_ticket(
        tickets_user, tickets_db, 9, 4, 5, TicketUpdate(section_id=8)
    )

    assert result is ticket
    assert ticket.section_id == 8
    tickets_db.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("data", "detail"),
    [
        (TicketUpdate(), "Provide at least one field to update"),
        (TicketUpdate(name=None), "Ticket name cannot be null"),
        (TicketUpdate(description=None), "Ticket description cannot be null"),
        (TicketUpdate(assignee_ids=None), "Assignee IDs cannot be null"),
        (TicketUpdate(section_id=None), "Section ID cannot be null"),
    ],
)
@pytest.mark.asyncio
async def test_update_ticket_rejects_invalid_updates(
    monkeypatch, tickets_db, tickets_user, data, detail
):
    ticket = Ticket(
        id=5,
        name="Fix bug",
        description="Reproduce and fix",
        section_id=4,
        memberships=[],
    )
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    monkeypatch.setattr(service, "_get_ticket", AsyncMock(return_value=ticket))

    with pytest.raises(HTTPException) as exc_info:
        await service.update_ticket(tickets_user, tickets_db, 9, 4, 5, data)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert exc_info.value.detail == detail
    tickets_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_ticket_changes_provided_name_and_description(
    monkeypatch, tickets_db, tickets_user
):
    ticket = Ticket(id=5, name="Old", description="Old", section_id=4, memberships=[])
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    monkeypatch.setattr(service, "_get_ticket", AsyncMock(return_value=ticket))

    result = await service.update_ticket(
        tickets_user,
        tickets_db,
        9,
        4,
        5,
        TicketUpdate(name="New", description="Updated"),
    )

    assert result is ticket
    assert (ticket.name, ticket.description) == ("New", "Updated")
    tickets_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_ticket_rejects_assignee_outside_board(
    monkeypatch, tickets_db, tickets_user
):
    ticket = Ticket(
        id=5,
        name="Fix bug",
        description="Details",
        section_id=4,
        memberships=[],
    )
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    monkeypatch.setattr(service, "_get_ticket", AsyncMock(return_value=ticket))
    monkeypatch.setattr(
        service,
        "_validated_assignee_ids",
        AsyncMock(
            side_effect=HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="All assignees must be members of the board",
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.update_ticket(
            tickets_user, tickets_db, 9, 4, 5, TicketUpdate(assignee_ids=[88])
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    tickets_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_archived_tickets_returns_only_archived_items(
    monkeypatch, tickets_db, tickets_user
):
    archived_ticket = Ticket(
        id=6,
        name="Old task",
        description="Archived task",
        section_id=4,
        is_archived=True,
        memberships=[],
    )
    db_result = MagicMock()
    db_result.scalars.return_value.all.return_value = [archived_ticket]
    tickets_db.execute.return_value = db_result
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())

    result = await service.list_archived_tickets(tickets_user, tickets_db, 9, 4)

    assert result == [archived_ticket]


@pytest.mark.asyncio
async def test_assignees_must_be_board_members(tickets_db):
    scalar_result = MagicMock()
    scalar_result.all.return_value = [1]
    db_result = MagicMock()
    db_result.scalars.return_value = scalar_result
    tickets_db.execute.return_value = db_result

    with pytest.raises(HTTPException) as exc_info:
        await service._validated_assignee_ids(tickets_db, 9, [1, 2])

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert exc_info.value.detail == "All assignees must be members of the board"


@pytest.mark.asyncio
async def test_soft_delete_archives_ticket(monkeypatch, tickets_db, tickets_user):
    ticket = SimpleNamespace(is_archived=False)
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    monkeypatch.setattr(service, "_get_ticket", AsyncMock(return_value=ticket))

    result = await service.soft_delete_ticket(tickets_user, tickets_db, 9, 4, 5)

    assert result is None
    assert ticket.is_archived is True
    tickets_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_hard_delete_requires_archived_ticket(
    monkeypatch, tickets_db, tickets_user
):
    ticket = SimpleNamespace(is_archived=False)
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    get_ticket = AsyncMock(return_value=ticket)
    monkeypatch.setattr(service, "_get_ticket", get_ticket)

    with pytest.raises(HTTPException) as exc_info:
        await service.hard_delete_ticket(tickets_user, tickets_db, 9, 4, 5)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Archive the ticket first"
    get_ticket.assert_awaited_once_with(tickets_db, 4, 5, include_archived=True)
    tickets_db.delete.assert_not_awaited()
    tickets_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_hard_delete_removes_archived_ticket(
    monkeypatch, tickets_db, tickets_user
):
    ticket = SimpleNamespace(is_archived=True)
    monkeypatch.setattr(service, "_require_section_role", AsyncMock())
    monkeypatch.setattr(service, "_get_ticket", AsyncMock(return_value=ticket))

    result = await service.hard_delete_ticket(tickets_user, tickets_db, 9, 4, 5)

    assert result is None
    tickets_db.delete.assert_awaited_once_with(ticket)
    tickets_db.commit.assert_awaited_once()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "x" * 101),
        ("description", ""),
        ("description", "x" * 301),
    ],
)
def test_ticket_create_rejects_values_outside_schema_limits(field, value):
    payload = {"name": "Valid", "description": "Valid"}
    payload[field] = value
    with pytest.raises(ValidationError):
        TicketCreate(**payload)


def test_ticket_response_serializes_memberships():
    ticket = SimpleNamespace(
        id=5,
        name="Fix bug",
        description="Reproduce and fix",
        is_archived=False,
        section_id=4,
        memberships=[SimpleNamespace(user_id=1, role=TicketRole.CREATOR)],
    )

    response = TicketResponse.model_validate(ticket)

    assert response.model_dump() == {
        "id": 5,
        "name": "Fix bug",
        "description": "Reproduce and fix",
        "is_archived": False,
        "section_id": 4,
        "memberships": [{"user_id": 1, "role": TicketRole.CREATOR}],
    }