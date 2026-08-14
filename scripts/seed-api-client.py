"""Idempotently seed two explicitly local POC API clients."""

import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from app.api.dependencies import hash_api_key
from app.config import get_settings
from app.persistence.db import Database
from app.persistence.models import ApiClientRow

_SCOPES = ["evaluation:submit", "evaluation:read", "evaluation:review"]


async def main() -> None:
    clients = [
        ("project-a", os.environ["AI_EVAL_DEMO_PROJECT_A_KEY"]),
        ("project-b", os.environ["AI_EVAL_DEMO_PROJECT_B_KEY"]),
    ]
    now = datetime.now(UTC)
    async with Database(get_settings().database_url) as database:
        async with database.sessions.begin() as session:
            for project_id, raw_key in clients:
                statement = insert(ApiClientRow).values(
                    project_id=project_id,
                    key_hash=hash_api_key(raw_key),
                    scopes=_SCOPES,
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
                statement = statement.on_conflict_do_update(
                    index_elements=[ApiClientRow.key_hash],
                    set_={
                        "project_id": project_id,
                        "scopes": _SCOPES,
                        "enabled": True,
                        "updated_at": now,
                    },
                )
                await session.execute(statement)


if __name__ == "__main__":
    asyncio.run(main())
