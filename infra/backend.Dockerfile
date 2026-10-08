FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true

RUN pip install --no-cache-dir poetry==2.4.0
WORKDIR /app/backend
COPY backend/pyproject.toml backend/poetry.lock ./
RUN poetry sync --only main --no-root
COPY backend/src ./src
RUN poetry install --only main

ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "freight_ecommerce.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
