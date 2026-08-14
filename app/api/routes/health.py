from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready", response_model=None)
async def ready(request: Request) -> dict[str, str] | JSONResponse:
    try:
        async with request.app.state.database.sessions() as session:
            if await session.scalar(text("SELECT 1")) != 1:
                raise RuntimeError("database check failed")
            revision = await session.scalar(
                text("SELECT version_num FROM alembic_version")
            )
        if revision != "0001_platform_poc":
            raise RuntimeError("migration check failed")
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}
