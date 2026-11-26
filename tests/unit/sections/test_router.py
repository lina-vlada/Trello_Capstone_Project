from unittest.mock import AsyncMock, patch
import pytest
from modules.sections import router as sections_router
from modules.sections.schemas import SectionCreate, SectionUpdate


@pytest.mark.asyncio
async def test_list_archived_board_sections_forwards_request(sections_db, sections_user):
    sections = [object()]

    with patch.object(
        sections_router,
        "list_archived_sections",
        new_callable=AsyncMock,
        return_value=sections,
    ) as list_archived:
        result = await sections_router.list_archived_board_sections(
            8, sections_user, sections_db
        )

    assert result == sections
    list_archived.assert_awaited_once_with(sections_user, sections_db, 8)


@pytest.mark.asyncio
async def test_list_board_sections_forwards_request(sections_db, sections_user):
    sections = [object()]

    with patch.object(
        sections_router, "list_sections", new_callable=AsyncMock, return_value=sections
    ) as list_sections:
        result = await sections_router.list_board_sections(8, sections_user, sections_db)

    assert result == sections
    list_sections.assert_awaited_once_with(sections_user, sections_db, 8)


@pytest.mark.asyncio
async def test_get_board_section_forwards_ids_and_dependencies(sections_db, sections_user):
    section = object()

    with patch.object(
        sections_router, "get_section", new_callable=AsyncMock, return_value=section
    ) as get_section:
        result = await sections_router.get_board_section(8, 3, sections_user, sections_db)

    assert result is section
    get_section.assert_awaited_once_with(sections_user, sections_db, 8, 3)


@pytest.mark.asyncio
async def test_create_board_section_forwards_request(sections_db, sections_user):
    data = SectionCreate(name="Ready")
    section = object()

    with patch.object(
        sections_router, "create_section", new_callable=AsyncMock, return_value=section
    ) as create_section:
        result = await sections_router.create_board_section(
            8, data, sections_user, sections_db
        )

    assert result is section
    create_section.assert_awaited_once_with(sections_user, sections_db, 8, data)


@pytest.mark.asyncio
async def test_restore_board_section_forwards_ids_and_dependencies(sections_db, sections_user):
    section = object()

    with patch.object(
        sections_router, "restore_section", new_callable=AsyncMock, return_value=section
    ) as restore_section:
        result = await sections_router.restore_board_section(
            8, 3, sections_user, sections_db
        )

    assert result is section
    restore_section.assert_awaited_once_with(sections_user, sections_db, 8, 3)


@pytest.mark.asyncio
async def test_update_board_section_forwards_update_data(sections_db, sections_user):
    data = SectionUpdate(name="Updated")
    section = object()

    with patch.object(
        sections_router, "update_section", new_callable=AsyncMock, return_value=section
    ) as update_section:
        result = await sections_router.update_board_section(
            8, 3, data, sections_user, sections_db
        )

    assert result is section
    update_section.assert_awaited_once_with(sections_user, sections_db, 8, 3, data)


@pytest.mark.asyncio
async def test_archive_board_section_forwards_ids(sections_db, sections_user):
    with patch.object(
        sections_router, "soft_delete_section", new_callable=AsyncMock
    ) as soft_delete:
        result = await sections_router.archive_board_section(
            8, 3, sections_user, sections_db
        )

    assert result is None
    soft_delete.assert_awaited_once_with(sections_user, sections_db, 8, 3)


@pytest.mark.asyncio
async def test_permanently_delete_board_section_forwards_ids(sections_db, sections_user):
    with patch.object(
        sections_router, "hard_delete_section", new_callable=AsyncMock
    ) as hard_delete:
        result = await sections_router.permanently_delete_board_section(
            8, 3, sections_user, sections_db
        )

    assert result is None
    hard_delete.assert_awaited_once_with(sections_user, sections_db, 8, 3)
