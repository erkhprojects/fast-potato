FROM python:3.14-slim AS deps

WORKDIR /app

# Install uv from the official pre-built image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy dependency specifications for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (without the project root itself yet for caching)
RUN uv sync --frozen --no-install-project --all-extras

FROM deps AS test

# Copy the entire workspace
COPY . .

# Install the project itself in editable/develop mode
RUN uv sync --frozen --all-extras

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
