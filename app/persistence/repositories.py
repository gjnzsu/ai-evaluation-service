from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.persistence.models import (
    EvaluationJobRow,
    EvaluationResultRow,
    EvaluationReviewRow,
    EvaluationRow,
)

SessionFactory = async_sessionmaker[AsyncSession]


class EvaluationRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def create_with_job(
        self,
        project_id: str,
        idempotency_key: str,
        request_payload: dict,
        request_hash: str,
    ) -> tuple[EvaluationRow, bool]:
        existing = await self._find_by_key(project_id, idempotency_key)
        if existing is not None:
            return self._replay(existing, request_hash)

        now = datetime.now(UTC)
        evaluation = EvaluationRow(
            project_id=project_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            request_payload=request_payload,
            artifact_type=str(request_payload.get("artifact_type", "")),
            execution_status="queued",
            created_at=now,
            updated_at=now,
        )
        try:
            async with self._sessions.begin() as session:
                session.add(evaluation)
                await session.flush()
                session.add(
                    EvaluationJobRow(
                        evaluation_id=evaluation.id,
                        status="queued",
                        attempt_count=0,
                        available_at=now,
                        lease_owner=None,
                        lease_expires_at=None,
                        lease_recovery_count=0,
                        last_error_code=None,
                        last_error_message=None,
                    )
                )
                await session.flush()
        except IntegrityError:
            existing = await self._find_by_key(project_id, idempotency_key)
            if existing is None:
                raise
            return self._replay(existing, request_hash)
        return evaluation, True

    async def _find_by_key(
        self, project_id: str, idempotency_key: str
    ) -> EvaluationRow | None:
        async with self._sessions() as session:
            return await session.scalar(
                select(EvaluationRow).where(
                    EvaluationRow.project_id == project_id,
                    EvaluationRow.idempotency_key == idempotency_key,
                )
            )

    @staticmethod
    def _replay(existing: EvaluationRow, request_hash: str) -> tuple[EvaluationRow, bool]:
        if existing.request_hash != request_hash:
            raise ValueError("idempotency key already refers to a different request")
        return existing, False

    async def get_for_project(
        self, evaluation_id: UUID, project_id: str
    ) -> EvaluationRow | None:
        async with self._sessions() as session:
            statement = select(EvaluationRow).where(
                EvaluationRow.id == evaluation_id,
                EvaluationRow.project_id == project_id,
            )
            return await session.scalar(statement)

    async def list_for_project(
        self,
        project_id: str,
    ) -> list[EvaluationRow]:
        statement = (
            select(EvaluationRow)
            .where(EvaluationRow.project_id == project_id)
            .order_by(EvaluationRow.created_at.desc(), EvaluationRow.id)
        )
        async with self._sessions() as session:
            rows: Sequence[EvaluationRow] = (await session.scalars(statement)).all()
            return list(rows)

    async def get_result_for_project(
        self, evaluation_id: UUID, project_id: str
    ) -> EvaluationResultRow | None:
        statement = (
            select(EvaluationResultRow)
            .join(EvaluationRow, EvaluationRow.id == EvaluationResultRow.evaluation_id)
            .where(
                EvaluationResultRow.evaluation_id == evaluation_id,
                EvaluationRow.project_id == project_id,
            )
        )
        async with self._sessions() as session:
            return await session.scalar(statement)

    async def list_page_for_project(
        self,
        project_id: str,
        *,
        page: int,
        page_size: int,
        artifact_type: str | None = None,
        execution_status: str | None = None,
        machine_verdict: str | None = None,
        review_status: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> tuple[
        list[tuple[EvaluationRow, EvaluationResultRow | None, EvaluationReviewRow | None]],
        int,
    ]:
        latest_review = aliased(EvaluationReviewRow)
        latest_review_id = (
            select(EvaluationReviewRow.id)
            .where(EvaluationReviewRow.evaluation_id == EvaluationRow.id)
            .order_by(EvaluationReviewRow.created_at.desc(), EvaluationReviewRow.id.desc())
            .limit(1)
            .correlate(EvaluationRow)
            .scalar_subquery()
        )
        effective_review_status = case(
            (latest_review.id.is_not(None), latest_review.decision),
            (EvaluationResultRow.machine_verdict == "pass", "optional"),
            (EvaluationResultRow.machine_verdict == "not_passed", "required"),
            else_=None,
        )
        conditions = [EvaluationRow.project_id == project_id]
        if artifact_type is not None:
            conditions.append(EvaluationRow.artifact_type == artifact_type)
        if execution_status is not None:
            conditions.append(EvaluationRow.execution_status == execution_status)
        if machine_verdict is not None:
            conditions.append(EvaluationResultRow.machine_verdict == machine_verdict)
        if review_status is not None:
            conditions.append(effective_review_status == review_status)
        if created_from is not None:
            conditions.append(EvaluationRow.created_at >= created_from)
        if created_to is not None:
            conditions.append(EvaluationRow.created_at <= created_to)

        base = (
            select(EvaluationRow, EvaluationResultRow, latest_review)
            .outerjoin(
                EvaluationResultRow,
                EvaluationResultRow.evaluation_id == EvaluationRow.id,
            )
            .outerjoin(latest_review, latest_review.id == latest_review_id)
            .where(*conditions)
        )
        statement = (
            base.order_by(EvaluationRow.created_at.desc(), EvaluationRow.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        count_statement = select(func.count()).select_from(base.subquery())
        async with self._sessions() as session:
            records = list((await session.execute(statement)).tuples().all())
            total = int(await session.scalar(count_statement) or 0)
        return records, total


class JobRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def insert_result(
        self,
        *,
        evaluation_id: UUID,
        deterministic_result: dict,
        machine_verdict: str,
        evaluator_version: str,
        llm_judge_result: dict | None,
        warnings: list[dict],
        completed_at: datetime,
    ) -> EvaluationResultRow:
        if any(warning != {"code": "judge_degraded"} for warning in warnings):
            raise ValueError("warning must use the safe judge_degraded contract")
        result = EvaluationResultRow(
            evaluation_id=evaluation_id,
            deterministic_result=deterministic_result,
            machine_verdict=machine_verdict,
            evaluator_version=evaluator_version,
            llm_judge_result=llm_judge_result,
            warnings=warnings,
            completed_at=completed_at,
        )
        async with self._sessions.begin() as session:
            session.add(result)
            await session.flush()
        return result


class ReviewRepository:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def append(
        self,
        *,
        project_id: str,
        evaluation_id: UUID,
        reviewer_id: str,
        decision: str,
        reason: str,
        waiver_rationale: str | None,
    ) -> EvaluationReviewRow | None:
        async with self._sessions.begin() as session:
            owned_evaluation = await session.scalar(
                select(EvaluationRow.id).where(
                    EvaluationRow.id == evaluation_id,
                    EvaluationRow.project_id == project_id,
                )
            )
            if owned_evaluation is None:
                return None
            review = EvaluationReviewRow(
                evaluation_id=evaluation_id,
                reviewer_id=reviewer_id,
                decision=decision,
                reason=reason,
                waiver_rationale=waiver_rationale,
                created_at=datetime.now(UTC),
            )
            session.add(review)
            await session.flush()
        return review

    async def list_for_project(
        self, evaluation_id: UUID, project_id: str
    ) -> list[EvaluationReviewRow]:
        statement = (
            select(EvaluationReviewRow)
            .join(EvaluationRow, EvaluationRow.id == EvaluationReviewRow.evaluation_id)
            .where(
                EvaluationReviewRow.evaluation_id == evaluation_id,
                EvaluationRow.project_id == project_id,
            )
            .order_by(EvaluationReviewRow.created_at, EvaluationReviewRow.id)
        )
        async with self._sessions() as session:
            return list((await session.scalars(statement)).all())
