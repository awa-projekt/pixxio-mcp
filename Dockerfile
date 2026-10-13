FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN useradd --system --uid 10001 app
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md LICENSE NOTICE ./
COPY src src
RUN uv sync --frozen --no-dev
ENV PATH=/app/.venv/bin:$PATH PIXXIO_MCP_HOST=0.0.0.0
USER app
EXPOSE 8000
CMD ["pixxio-mcp"]
