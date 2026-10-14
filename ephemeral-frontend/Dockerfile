# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml* .dsfr.yml ./
RUN pnpm install --frozen-lockfile
COPY . .
# VITE_API_BASE_URL is baked in at build time. Empty (default) means relative
# URLs, which works when frontend and backend share the same host (K8s ingress).
# For split-host setups (docker-compose dev), pass --build-arg VITE_API_BASE_URL=http://localhost:8000.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
# URL du frontend MilleFeuille complet, pour le lien de renvoi (vide = pas de lien).
ARG VITE_MILLEFEUILLE_URL=""
ENV VITE_MILLEFEUILLE_URL=$VITE_MILLEFEUILLE_URL
RUN pnpm build

# nginxinc/nginx-unprivileged already runs as the unprivileged `nginx` user
# (uid 101) and listens on 8080 instead of 80, so no extra port setup is
# required to get a non-root container. USER is repeated explicitly below
# anyway: Trivy's Dockerfile config scan (DS-0002) reads the Dockerfile
# text, not the base image's own config, and flags a missing USER line.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY --chown=nginx:nginx docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chown=nginx:nginx --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8080/ >/dev/null || exit 1
