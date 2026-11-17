from fastapi import APIRouter, status
from lib.database.postgres import SessionDep
from modules.auth.dependencies import UserDep
from modules.sections.schemas import SectionCreate, SectionResponse, SectionUpdate
from modules.sections.service import (
	create_section,
	get_section,
	hard_delete_section,
	list_sections,
	soft_delete_section,
	update_section,
)

router = APIRouter(prefix="/boards/{board_id}/sections", tags=["Sections management"])


@router.get("/", response_model=list[SectionResponse])
async def list_board_sections(board_id: int, user: UserDep, db: SessionDep):
	return await list_sections(user, db, board_id)


@router.get("/{section_id}", response_model=SectionResponse)
async def get_board_section(board_id: int, section_id: int, user: UserDep, db: SessionDep):
	return await get_section(user, db, board_id, section_id)


@router.post("/", response_model=SectionResponse, status_code=status.HTTP_201_CREATED)
async def create_board_section(board_id: int, data: SectionCreate, user: UserDep, db: SessionDep):
	return await create_section(user, db, board_id, data)


@router.patch("/{section_id}", response_model=SectionResponse)
async def update_board_section(board_id: int, section_id: int, data: SectionUpdate, user: UserDep, db: SessionDep):
	return await update_section(user, db, board_id, section_id, data)


@router.delete("/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_board_section(board_id: int, section_id: int, user: UserDep, db: SessionDep) -> None:
	await soft_delete_section(user, db, board_id, section_id)


@router.delete("/{section_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
async def permanently_delete_board_section(board_id: int, section_id: int, user: UserDep, db: SessionDep) -> None:
	await hard_delete_section(user, db, board_id, section_id)


