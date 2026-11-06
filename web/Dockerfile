# The web app, built once and served by nginx, which also passes /api to the API container.
FROM node:22-alpine AS build
RUN npm install -g pnpm@10.7.0
WORKDIR /repo/web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web ./
COPY docs ../docs
RUN pnpm exec vite build

FROM nginx:1.27-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/web/dist /usr/share/nginx/html
EXPOSE 80
