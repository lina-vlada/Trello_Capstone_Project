from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import status
from fastapi.exceptions import HTTPException
from pydantic import ValidationError
from entities.board_user import BoardRole
from modules.sections import service
from modules.sections.schemas import SectionCreate, SectionResponse, SectionUpdate


@pytest.mark.asyncio
async def test_get_section_loads_tickets_and_returns_section(sections_db):
    section = SimpleNamespace(id=3, tickets=[])
    result = MagicMock()
    result.scalar_one_or_none.return_value = section
    sections_db.execute.return_value = result

    returned = await service._get_section(sections_db, 8, 3)

    assert returned is section
    sections_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_section_returns_not_found_for_unknown_section(sections_db):
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    sections_db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await service._get_section(sections_db, 8, 3)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Section not found"


@pytest.mark.asyncio
async def test_require_board_role_delegates_to_existing_board_access_check(monkeypatch, sections_db):
    board_access_check = AsyncMock()
    monkeypatch.setattr(service, "_get_board_for_user", board_access_check)

    await service._require_board_role(
        sections_db, 1, 8, {BoardRole.OWNER, BoardRole.EDITOR}
    )

    board_access_check.assert_awaited_once_with(
        sections_db, 1, 8, {BoardRole.OWNER, BoardRole.EDITOR}
    )


@pytest.mark.asyncio
async def test_list_sections_returns_active_sections_for_board(monkeypatch, sections_db, sections_user):
    sections = [SimpleNamespace(id=3, tickets=[]), SimpleNamespace(id=4, tickets=[])]
    result = MagicMock()
    result.scalars.return_value.all.return_value = sections
    sections_db.execute.return_value = result
    require_role = AsyncMock()
    monkeypatch.setattr(service, "_require_board_role", require_role)

    returned = await service.list_sections(sections_user, sections_db, 8)

    assert returned == sections
    require_role.assert_awaited_once_with(
        sections_db, 1, 8, {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER}
    )
    sections_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_archived_sections_returns_archived_sections(monkeypatch, sections_db, sections_user):
    sections = [SimpleNamespace(id=7, tickets=[])]
    result = MagicMock()
    result.scalars.return_value.all.return_value = sections
    sections_db.execute.return_value = result
    require_role = AsyncMock()
    monkeypatch.setattr(service, "_require_board_role", require_role)

    returned = await service.list_archived_sections(sections_user, sections_db, 8)

    assert returned == sections
    require_role.assert_awaited_once_with(
        sections_db, 1, 8, {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER}
    )
    sections_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_section_checks_access_and_returns_active_section(monkeypatch, sections_db, sections_user):
    section = SimpleNamespace(is_archived=False)
    require_role = AsyncMock()
    get_section = AsyncMock(return_value=section)
    monkeypatch.setattr(service, "_require_board_role", require_role)
    monkeypatch.setattr(service, "_get_section", get_section)

    returned = await service.get_section(sections_user, sections_db, 8, 3)

    assert returned is section
    require_role.assert_awaited_once_with(
        sections_db,
        1,
        8,
        {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER},
    )
    get_section.assert_awaited_once_with(sections_db, 8, 3)


@pytest.mark.asyncio
async def test_get_section_hides_archived_section(monkeypatch, sections_db, sections_user):
    section = SimpleNamespace(is_archived=True)
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(service, "_get_section", AsyncMock(return_value=section))

    with pytest.raises(HTTPException) as exc_info:
        await service.get_section(sections_user, sections_db, 8, 3)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_create_section_requires_editor_or_owner(monkeypatch, sections_db, sections_user):
    require_role = AsyncMock(side_effect=HTTPException(status.HTTP_403_FORBIDDEN))
    monkeypatch.setattr(service, "_require_board_role", require_role)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_section(
            sections_user, sections_db, 8, SectionCreate(name="Ready")
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    sections_db.add.assert_not_called()
    sections_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_section_adds_section_to_board(monkeypatch, sections_db, sections_user):
    require_role = AsyncMock()
    monkeypatch.setattr(service, "_require_board_role", require_role)

    section = await service.create_section(
        sections_user, sections_db, 8, SectionCreate(name="Ready", description="Work queue")
    )

    assert section is sections_db.add.call_args.args[0]
    assert (section.name, section.description, section.board_id) == (
        "Ready",
        "Work queue",
        8,
    )
    assert section.tickets == []
    require_role.assert_awaited_once_with(
        sections_db, 1, 8, {BoardRole.OWNER, BoardRole.EDITOR}
    )
    sections_db.commit.assert_awaited_once()
    sections_db.refresh.assert_awaited_once_with(
        section,
        attribute_names=["id", "name", "description", "board_id", "is_archived"],
    )


@pytest.mark.asyncio
async def test_update_section_changes_only_provided_fields(monkeypatch, sections_db, sections_user):
    section = SimpleNamespace(name="Old", description="Keep", is_archived=False)
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(service, "_get_section", AsyncMock(return_value=section))

    result = await service.update_section(
        sections_user, sections_db, 8, 3, SectionUpdate(name="New")
    )

    assert result is section
    assert (section.name, section.description) == ("New", "Keep")
    sections_db.commit.assert_awaited_once()
    sections_db.refresh.assert_awaited_once_with(section)


@pytest.mark.parametrize(
    ("data", "detail"),
    [
        (SectionUpdate(), "Provide at least one field to update"),
        (SectionUpdate(name=None), "Section name cannot be null"),
    ],
)
@pytest.mark.asyncio
async def test_update_section_rejects_invalid_updates(monkeypatch, sections_db, sections_user, data, detail):
    section = SimpleNamespace(is_archived=False)
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(service, "_get_section", AsyncMock(return_value=section))

    with pytest.raises(HTTPException) as exc_info:
        await service.update_section(sections_user, sections_db, 8, 3, data)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert exc_info.value.detail == detail
    sections_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_section_hides_archived_section(monkeypatch, sections_db, sections_user):
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(
        service,
        "_get_section",
        AsyncMock(return_value=SimpleNamespace(is_archived=True)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.update_section(
            sections_user, sections_db, 8, 3, SectionUpdate(name="Renamed")
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    sections_db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "x" * 101),
        ("description", "x" * 301),
    ],
)
def test_section_create_rejects_values_outside_schema_limits(field, value):
    with pytest.raises(ValidationError):
        SectionCreate(**{field: value})


@pytest.mark.asyncio
async def test_soft_delete_archives_section_and_its_tickets(monkeypatch, sections_db, sections_user):
    tickets = [SimpleNamespace(is_archived=False), SimpleNamespace(is_archived=False)]
    section = SimpleNamespace(is_archived=False, tickets=tickets)
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(service, "_get_section", AsyncMock(return_value=section))

    await service.soft_delete_section(sections_user, sections_db, 8, 3)

    assert section.is_archived is True
    assert all(ticket.is_archived for ticket in tickets)
    sections_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_soft_delete_hides_already_archived_section(monkeypatch, sections_db, sections_user):
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(
        service,
        "_get_section",
        AsyncMock(return_value=SimpleNamespace(is_archived=True)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.soft_delete_section(sections_user, sections_db, 8, 3)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    sections_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_soft_delete_handles_missing_ticket_relationship(monkeypatch, sections_db, sections_user):
    section = SimpleNamespace(is_archived=False)
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(service, "_get_section", AsyncMock(return_value=section))

    await service.soft_delete_section(sections_user, sections_db, 8, 3)

    assert section.is_archived is True
    sections_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_hard_delete_requires_archived_section(monkeypatch, sections_db, sections_user):
    section = SimpleNamespace(is_archived=False)
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(service, "_get_section", AsyncMock(return_value=section))

    with pytest.raises(HTTPException) as exc_info:
        await service.hard_delete_section(sections_user, sections_db, 8, 3)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Archive the section before permanently deleting it"
    sections_db.delete.assert_not_awaited()
    sections_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_hard_delete_removes_archived_section(monkeypatch, sections_db, sections_user):
    section = SimpleNamespace(is_archived=True)
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(service, "_get_section", AsyncMock(return_value=section))

    await service.hard_delete_section(sections_user, sections_db, 8, 3)

    sections_db.delete.assert_awaited_once_with(section)
    sections_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_restore_section_reactivates_archived_section(monkeypatch, sections_db, sections_user):
    section = SimpleNamespace(is_archived=True)
    require_role = AsyncMock()
    get_section = AsyncMock(return_value=section)
    monkeypatch.setattr(service, "_require_board_role", require_role)
    monkeypatch.setattr(service, "_get_section", get_section)

    result = await service.restore_section(sections_user, sections_db, 8, 3)

    assert result is section
    assert section.is_archived is False
    require_role.assert_awaited_once_with(
        sections_db, 1, 8, {BoardRole.OWNER, BoardRole.EDITOR}
    )
    get_section.assert_awaited_once_with(sections_db, 8, 3)
    sections_db.commit.assert_awaited_once()
    sections_db.refresh.assert_awaited_once_with(section)


@pytest.mark.asyncio
async def test_restore_section_rejects_active_section(monkeypatch, sections_db, sections_user):
    section = SimpleNamespace(is_archived=False)
    monkeypatch.setattr(service, "_require_board_role", AsyncMock())
    monkeypatch.setattr(service, "_get_section", AsyncMock(return_value=section))

    with pytest.raises(HTTPException) as exc_info:
        await service.restore_section(sections_user, sections_db, 8, 3)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Section is already active"
    sections_db.commit.assert_not_awaited()


def test_section_response_serializes_model_fields():
    section = SimpleNamespace(
        id=3,
        name="Ready",
        description="Work queue",
        is_archived=False,
        board_id=8,
        tickets=[
            SimpleNamespace(
                id=4,
                name="Pick up",
                description="Start work",
                is_archived=False,
                section_id=3,
            )
        ],
    )

    response = SectionResponse.model_validate(section)

    assert response.model_dump() == {
        "id": 3,
        "name": "Ready",
        "description": "Work queue",
        "is_archived": False,
        "board_id": 8,
        "tickets": [
            {
                "id": 4,
                "name": "Pick up",
                "description": "Start work",
                "is_archived": False,
                "section_id": 3,
            }
        ],
    }