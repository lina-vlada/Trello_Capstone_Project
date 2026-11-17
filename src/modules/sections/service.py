from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from entities.board_user import BoardRole
from entities.section import Section
from lib.database.postgres import SessionDep
from modules.auth.dependencies import UserDep
from modules.boards.service import _require_board_role
from modules.sections.schemas import SectionCreate, SectionUpdate


async def _get_section(db: SessionDep, board_id: int, section_id: int) -> Section:
	result = await db.execute(
		select(Section)
		.options(selectinload(Section.tickets))
		.where(Section.id == section_id, Section.board_id == board_id)
	)
	section = result.scalar_one_or_none()
	if section is None:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
	return section


async def list_sections(user: UserDep, db: SessionDep, board_id: int) -> list[Section]:
	await _require_board_role(db, user.id, board_id, {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER})
	result = await db.execute(
		select(Section)
		.options(selectinload(Section.tickets))
		.where(Section.board_id == board_id, Section.is_archived.is_(False))
	)
	return result.scalars().all()


async def get_section(user: UserDep, db: SessionDep, board_id: int, section_id: int) -> Section:
	await _require_board_role(db, user.id, board_id, {BoardRole.OWNER, BoardRole.EDITOR, BoardRole.VIEWER})
	section = await _get_section(db, board_id, section_id)
	if section.is_archived:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
	return section


async def create_section(user: UserDep, db: SessionDep, board_id: int, data: SectionCreate) -> Section:
	await _require_board_role(db, user.id, board_id, {BoardRole.OWNER, BoardRole.EDITOR})
	section = Section(name=data.name, description=data.description, board_id=board_id, tickets=[])
	db.add(section)
	await db.commit()
	await db.refresh(section)
	return section


async def update_section(user: UserDep, db: SessionDep, board_id: int, section_id: int, data: SectionUpdate) -> Section:
	await _require_board_role(db, user.id, board_id, {BoardRole.OWNER, BoardRole.EDITOR})
	section = await _get_section(db, board_id, section_id)
	if section.is_archived:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
	updates = data.model_dump(exclude_unset=True)
	if not updates:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="Provide at least one field to update",
		)
	if "name" in updates and updates["name"] is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="Section name cannot be null",
		)
	for field, value in updates.items():
		setattr(section, field, value)
	await db.commit()
	await db.refresh(section)
	return section


async def soft_delete_section(user: UserDep, db: SessionDep, board_id: int, section_id: int) -> None:
	await _require_board_role(db, user.id, board_id, {BoardRole.OWNER, BoardRole.EDITOR})
	section = await _get_section(db, board_id, section_id)
	if section.is_archived:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
	section.is_archived = True
	await db.commit()


async def hard_delete_section(user: UserDep, db: SessionDep, board_id: int, section_id: int) -> None:
	await _require_board_role(db, user.id, board_id, {BoardRole.OWNER})
	section = await _get_section(db, board_id, section_id)
	if not section.is_archived:
		raise HTTPException(
			status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
			detail="Archive the section first",
		)
	await db.delete(section)
	await db.commit()
