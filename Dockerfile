FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /service

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
ARG INSTALL_JEV=false
RUN if [ "$INSTALL_JEV" = "true" ]; then python -m pip install '.[jev]'; else python -m pip install .; fi

USER 65532:65532

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
