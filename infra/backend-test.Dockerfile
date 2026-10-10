FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true

RUN pip install --no-cache-dir poetry==2.4.0
WORKDIR /app/backend
COPY LICENSE THIRD_PARTY_NOTICES.md /app/
COPY backend/pyproject.toml backend/poetry.lock ./
RUN poetry sync --with dev --no-root
COPY backend/src ./src
COPY backend/tests ./tests
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
RUN poetry install --with dev

RUN groupadd --system app \
    && useradd --system --create-home --gid app app \
    && chown -R app:app /app/backend

ENV PATH="/app/backend/.venv/bin:$PATH"
USER app
ENTRYPOINT ["testrunner"]
