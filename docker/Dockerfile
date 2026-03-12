FROM python:3.13-slim

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
COPY templates/ ./templates/

# Install dependencies
RUN uv sync --no-dev

WORKDIR /workspace

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV WORKSPACE_DIR=/workspace/files \
    SESSION_DIR=/workspace/session \
    PORT=8000

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
