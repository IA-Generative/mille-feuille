# syntax=docker/dockerfile:1

FROM node:26-alpine AS build
WORKDIR /app
# Node 25+ n'embarque plus corepack.
RUN npm install -g corepack && corepack enable
COPY package.json pnpm-lock.yaml* .dsfr.yml ./
RUN pnpm install --frozen-lockfile
COPY . .
# VITE_API_BASE_URL is baked in at build time. Empty (default) means relative
# URLs, which works when frontend and backend share the same host (K8s ingress).
# For split-host setups (docker-compose dev), pass --build-arg VITE_API_BASE_URL=http://localhost:8000.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN pnpm build

# nginxinc/nginx-unprivileged already runs as the unprivileged `nginx` user
# (uid 101) and listens on 8080 instead of 80, so no extra port setup is
# required to get a non-root container. USER is repeated explicitly below
# anyway: Trivy's Dockerfile config scan (DS-0002) reads the Dockerfile
# text, not the base image's own config, and flags a missing USER line.
FROM nginxinc/nginx-unprivileged:1.30-alpine AS runtime
# The base image is rebuilt rarely: pull the Alpine security fixes published since (openssl, libxml2, zlib, curl...).
# Needs root for apk; USER nginx below drops it again.
USER root
# nginx est épinglé (nginx=<version>) dans l'image de base, et ses modules exigent cette version exacte : `apk upgrade`
# seul laisse donc nginx en place. On retire les modules (inutilisés ici), puis on met nginx à jour avec le reste.
RUN apk del --no-cache $(apk info -q | grep '^nginx-module-' || true) \
 && apk add --no-cache --upgrade nginx \
 && apk upgrade --no-cache
COPY --chown=nginx:nginx docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chown=nginx:nginx --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:8080/ >/dev/null || exit 1
