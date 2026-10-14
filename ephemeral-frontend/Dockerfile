# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml* .dsfr.yml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Pas de variable VITE_* au build : l'adresse de l'API et le lien vers MilleFeuille se règlent au DÉMARRAGE du
# conteneur (API_BASE_URL, MILLEFEUILLE_URL, voir docker/40-runtime-config.sh), pour une seule image par version.
RUN pnpm build

# nginxinc/nginx-unprivileged already runs as the unprivileged `nginx` user
# (uid 101) and listens on 8080 instead of 80, so no extra port setup is
# required to get a non-root container. USER is repeated explicitly below
# anyway: Trivy's Dockerfile config scan (DS-0002) reads the Dockerfile
# text, not the base image's own config, and flags a missing USER line.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY --chown=nginx:nginx docker/nginx.conf /etc/nginx/conf.d/default.conf
# Lancé par l'entrypoint de l'image avant nginx : écrit /tmp/config.js (seul dossier inscriptible du conteneur).
COPY --chown=nginx:nginx --chmod=755 docker/40-runtime-config.sh /docker-entrypoint.d/40-runtime-config.sh
COPY --chown=nginx:nginx --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8080/ >/dev/null || exit 1
