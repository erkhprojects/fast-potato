FROM python:3.14-slim AS deps

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-root --all-extras

FROM deps AS test

COPY . .

ENV PYTHONPATH=/app
