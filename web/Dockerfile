# Se construye desde la raíz del repo (ver docker-compose.yml): la Biblioteca
# lee ../docs/biblioteca al compilar.

# Etapa 1: compilar el sitio estático de Astro.
FROM node:24-alpine AS build

WORKDIR /repo/web

RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ ./
COPY docs/biblioteca/ /repo/docs/biblioteca/

RUN pnpm exec astro build

# Etapa 2: servir lo compilado con nginx.
FROM nginx:1.29-alpine

COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/web/dist/ /usr/share/nginx/html/
RUN chmod -R a+rX /usr/share/nginx/html /etc/nginx/conf.d/default.conf

EXPOSE 80
