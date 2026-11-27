import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.factory import RequestContext, get_current_user
from app.db import get_db
from app.repositories.dossier_access_repository import DossierAccessRepository
from app.repositories.dossier_repository import DossierRepository
from app.repositories.user_directory_repository import UserDirectoryRepository
from app.schemas.dossier import PersonOut

# Annuaire local (issue #173) : les personnes qu'on peut proposer à l'affectation d'un dossier. Lecture seule ;
# l'annuaire est alimenté par les connexions. Avec `dossier_id`, seules les personnes qui ont accès à ce dossier
# sont proposées (#177).
router = APIRouter(prefix="/users", tags=["Annuaire"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[PersonOut])
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str | None, Query(max_length=100, description="Recherche sur le nom ou l'e-mail")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    dossier_id: Annotated[
        uuid.UUID | None, Query(description="Ne proposer que les personnes qui ont accès à ce dossier")
    ] = None,
    user: Annotated[RequestContext | None, Depends(get_current_user)] = None,
) -> list[PersonOut]:
    entitled_to = None
    if dossier_id is not None:
        dossier = await DossierRepository(db).get(dossier_id, user)  # 404 si je ne vois pas moi-même le dossier
        if dossier is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dossier introuvable")
        entitled_to = (
            dossier.visibility,
            dossier.analyse_id,
            await DossierAccessRepository(db).group_paths(dossier.id),
        )
    people = await UserDirectoryRepository(db).search(q, limit, entitled_to=entitled_to)
    return [PersonOut.model_validate(person, from_attributes=True) for person in people]
