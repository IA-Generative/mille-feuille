# syntax=docker/dockerfile:1
#
# Contexte de build : la RACINE du dépôt (le worker dépend des SDK du monorepo, sdks/python/).
#   GH_TOKEN=$(gh auth token) docker build -f worker/async_api/Dockerfile \
#     --secret id=github_token,env=GH_TOKEN -t mille-feuille-async-api-worker .
#
# `mic-worker` vient du dépôt PRIVÉ IA-Generative/async-api : le secret BuildKit `github_token`
# (jeton avec accès en lecture à ce dépôt) est nécessaire au build. Il n'est jamais écrit dans
# une couche : il n'existe que le temps de la commande `uv sync`.

FROM python:3.15-slim AS builder
# git : `mic-worker` (async-api) est installé depuis un dépôt Git, il n'est pas publié sur PyPI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# Même chemin relatif qu'en local : pyproject.toml référence ../../sdks/python/*.
WORKDIR /worker/async_api
COPY sdks/python/millefeuille /sdks/python/millefeuille
COPY sdks/python/millefeuille-ephemeral /sdks/python/millefeuille-ephemeral
COPY worker/async_api/pyproject.toml worker/async_api/uv.lock ./
RUN --mount=type=secret,id=github_token \
    GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0="url.https://x-access-token:$(cat /run/secrets/github_token)@github.com/.insteadOf" \
    GIT_CONFIG_VALUE_0="https://github.com/" \
    uv sync --frozen --no-dev

FROM python:3.15-slim AS runtime
# pip est un outil de build : l\'image d\'exécution n\'installe rien, et le pip livré avec l\'image de base porte des CVE
# connues. Retiré plutôt que mis à jour, il n\'y a rien à maintenir.
RUN python -m pip uninstall -y pip
RUN groupadd -g 1001 appuser && useradd -u 1001 -g 1001 -m -s /bin/bash appuser
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
COPY --from=builder --chown=appuser:appuser /worker/async_api/.venv /app/.venv
# Les SDK sont installés en editable : le venv pointe vers leurs sources, qui doivent suivre.
COPY --from=builder /sdks /sdks
COPY --chown=appuser:appuser worker/async_api/contrat.json worker/async_api/main.py ./
COPY --chown=appuser:appuser worker/async_api/src/ ./src/
USER appuser
EXPOSE 8084
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8084/health', timeout=3).status == 200 else 1)"
CMD ["python", "main.py"]
