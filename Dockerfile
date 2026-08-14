FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /service

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
RUN python -m pip install .

USER 65532:65532

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
