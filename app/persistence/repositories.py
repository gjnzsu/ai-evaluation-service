from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
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


@dataclass(frozen=True)
class ClaimedJob:
    evaluation_id: UUID
    request_payload: dict
    lease_owner: str
    lease_expires_at: datetime
    attempt_count: int
    lease_recovery_count: int


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
                        available_at=func.now(),
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
            (EvaluationResultRow.evaluation_id.is_(None), None),
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

    async def claim_next(
        self, lease_owner: str, *, lease_seconds: float
    ) -> ClaimedJob | None:
        statement = (
            select(EvaluationJobRow, EvaluationRow.request_payload)
            .join(EvaluationRow, EvaluationRow.id == EvaluationJobRow.evaluation_id)
            .where(
                or_(
                    and_(
                        EvaluationJobRow.status == "queued",
                        EvaluationJobRow.available_at <= func.now(),
                    ),
                    and_(
                        EvaluationJobRow.status == "running",
                        EvaluationJobRow.lease_expires_at < func.now(),
                    ),
                )
            )
            .order_by(EvaluationJobRow.available_at, EvaluationJobRow.evaluation_id)
            .with_for_update(of=EvaluationJobRow, skip_locked=True)
            .limit(1)
        )
        async with self._sessions.begin() as session:
            record = (await session.execute(statement)).one_or_none()
            if record is None:
                return None
            job, request_payload = record
            recovering = job.status == "running"
            job.status = "running"
            job.lease_owner = lease_owner
            job.lease_expires_at = func.now() + timedelta(seconds=lease_seconds)
            job.attempt_count += 1
            if recovering:
                job.lease_recovery_count += 1
            evaluation = await session.get(EvaluationRow, job.evaluation_id)
            if evaluation is None:
                return None
            evaluation.execution_status = "running"
            evaluation.updated_at = func.now()
            await session.flush()
            await session.refresh(job, attribute_names=["lease_expires_at"])
            return ClaimedJob(
                evaluation_id=job.evaluation_id,
                request_payload=request_payload,
                lease_owner=job.lease_owner,
                lease_expires_at=job.lease_expires_at,
                attempt_count=job.attempt_count,
                lease_recovery_count=job.lease_recovery_count,
            )

    async def renew_lease(
        self,
        evaluation_id: UUID,
        *,
        lease_owner: str,
        lease_seconds: float,
    ) -> EvaluationJobRow | None:
        async with self._sessions.begin() as session:
            job = await session.scalar(
                select(EvaluationJobRow)
                .where(
                    EvaluationJobRow.evaluation_id == evaluation_id,
                    EvaluationJobRow.status == "running",
                    EvaluationJobRow.lease_owner == lease_owner,
                )
                .with_for_update()
            )
            if job is None:
                return None
            job.lease_expires_at = func.now() + timedelta(seconds=lease_seconds)
            await session.flush()
            await session.refresh(job, attribute_names=["lease_expires_at"])
            return job

    async def complete(
        self,
        *,
        evaluation_id: UUID,
        lease_owner: str,
        deterministic_result: dict,
        machine_verdict: str,
        evaluator_version: str,
        llm_judge_result: dict | None,
        warnings: list[dict],
    ) -> bool:
        self._validate_warnings(warnings)
        now = datetime.now(UTC)
        async with self._sessions.begin() as session:
            job = await self._owned_running_job(session, evaluation_id, lease_owner)
            if job is None:
                return False
            session.add(
                EvaluationResultRow(
                    evaluation_id=evaluation_id,
                    deterministic_result=deterministic_result,
                    machine_verdict=machine_verdict,
                    evaluator_version=evaluator_version,
                    llm_judge_result=llm_judge_result,
                    warnings=warnings,
                    completed_at=now,
                )
            )
            evaluation = await session.get(EvaluationRow, evaluation_id)
            if evaluation is None:
                return False
            evaluation.execution_status = "completed"
            evaluation.updated_at = now
            job.status = "completed"
            job.lease_owner = None
            job.lease_expires_at = None
            job.last_error_code = None
            job.last_error_message = None
            await session.flush()
            return True

    async def fail(
        self,
        *,
        evaluation_id: UUID,
        lease_owner: str,
        error_code: str,
    ) -> bool:
        now = datetime.now(UTC)
        async with self._sessions.begin() as session:
            job = await self._owned_running_job(session, evaluation_id, lease_owner)
            if job is None:
                return False
            evaluation = await session.get(EvaluationRow, evaluation_id)
            if evaluation is None:
                return False
            evaluation.execution_status = "failed"
            evaluation.updated_at = now
            job.status = "failed"
            job.lease_owner = None
            job.lease_expires_at = None
            job.last_error_code = error_code
            job.last_error_message = None
            await session.flush()
            return True

    @staticmethod
    async def _owned_running_job(
        session: AsyncSession, evaluation_id: UUID, lease_owner: str
    ) -> EvaluationJobRow | None:
        return await session.scalar(
            select(EvaluationJobRow)
            .where(
                EvaluationJobRow.evaluation_id == evaluation_id,
                EvaluationJobRow.status == "running",
                EvaluationJobRow.lease_owner == lease_owner,
            )
            .with_for_update()
        )

    @staticmethod
    def _validate_warnings(warnings: list[dict]) -> None:
        if any(warning != {"code": "judge_degraded"} for warning in warnings):
            raise ValueError("warning must use the safe judge_degraded contract")

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
        self._validate_warnings(warnings)
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
