from fastapi import APIRouter, Depends

from app.core.security.factory import get_current_user
from app.schemas.tool import ToolOut
from app.services.tools.internal_catalog import INTERNAL_TOOLS

router = APIRouter(prefix="/tools", tags=["Tools"], dependencies=[Depends(get_current_user)])


@router.get("/internal", response_model=list[ToolOut])
async def list_internal_tools() -> list[ToolOut]:
    """Les tools internes de la plateforme (toujours disponibles, non modifiables)."""
    return [ToolOut.of_internal(tool) for tool in INTERNAL_TOOLS]
