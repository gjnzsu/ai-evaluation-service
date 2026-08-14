from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.observability.context import set_project_id
from app.persistence.db import Database
from app.persistence.models import ApiClientRow


@dataclass(frozen=True)
class AuthenticatedClient:
    project_id: str
    scopes: frozenset[str]


def hash_api_key(raw_key: str) -> str:
    return sha256(raw_key.encode("utf-8")).hexdigest()


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    async with database.sessions() as session:
        yield session


def authenticate_client(
    required_scope: str,
) -> Callable[..., Awaitable[AuthenticatedClient]]:
    async def dependency(
        session: Annotated[AsyncSession, Depends(get_database_session)],
        raw_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> AuthenticatedClient:
        if not raw_key:
            raise _invalid_api_key()

        candidate_hash = hash_api_key(raw_key)
        client = await session.scalar(
            select(ApiClientRow).where(ApiClientRow.key_hash == candidate_hash)
        )
        if (
            client is None
            or not compare_digest(client.key_hash, candidate_hash)
            or not client.enabled
        ):
            raise _invalid_api_key()

        scopes = frozenset(client.scopes)
        set_project_id(client.project_id)
        if required_scope not in scopes:
            raise ApiError(
                status_code=403,
                code="insufficient_scope",
                message=f"The API key does not grant {required_scope}.",
            )
        return AuthenticatedClient(project_id=client.project_id, scopes=scopes)

    return dependency


def _invalid_api_key() -> ApiError:
    return ApiError(
        status_code=401,
        code="invalid_api_key",
        message="The API key is missing, invalid, or disabled.",
    )
