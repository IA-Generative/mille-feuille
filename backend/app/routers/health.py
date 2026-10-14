import logging
from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Response, status

from app.connectors import db_connector, redis_connector, s3_connector
from app.schemas.health import Health, HealthReport, HealthStatus, VersionOut

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness check", response_model=HealthStatus)
def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/version", summary="Version du backend", response_model=VersionOut)
def backend_version() -> VersionOut:
    try:
        return VersionOut(version=version("mille-feuille-backend"))
    except PackageNotFoundError:
        return VersionOut(version="dev")


@router.get(
    "/health/ready",
    summary="Readiness check",
    response_model=HealthReport,
)
async def health_ready(response: Response) -> HealthReport:
    dependencies: list[Health] = [
        await db_connector.get_health(),
        redis_connector.get_health(),
        s3_connector.get_health(),
    ]
    api_status = "healthy"
    for dependency in dependencies:
        if dependency.status == "unhealthy":
            api_status = "unhealthy"
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            logger.error(
                "Readiness check failed: %s is unhealthy",
                dependency.name,
                extra={"dependency": dependency.name, "details": dependency.extras},
            )

    return HealthReport(name="mille-feuille-backend", status=api_status, dependencies=dependencies)
