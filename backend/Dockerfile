# syntax=docker/dockerfile:1

FROM python:3.15-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project
COPY app ./app
RUN uv sync --no-dev

FROM python:3.15-slim AS runtime
# pip est un outil de build : l\'image d\'exécution n\'installe rien, et le pip livré avec l\'image de base porte des CVE
# connues. Retiré plutôt que mis à jour, il n\'y a rien à maintenir.
RUN python -m pip uninstall -y pip
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/app /app/app
# Needed at runtime, not just build time: `alembic upgrade head` runs against
# the deployed image (docker compose's migrate service, an init container),
# so the migration scripts and alembic.ini have to travel with it.
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini ./
USER app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health',timeout=5).status==200 else 1)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
