FROM python:3.13-slim AS research
WORKDIR /app
COPY backend ./backend
COPY data ./data
COPY scripts ./scripts
COPY docs/research/global-sweep-20261110.json ./docs/research/global-sweep-20261110.json
RUN pip install --no-cache-dir -r backend/requirements.txt && python scripts/build_public.py

FROM node:22-alpine AS frontend
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
COPY --from=research /app/web/public/data ./public/data
ENV VITE_API_BASE=. VITE_BASE_PATH=/
RUN npm run build

FROM nginx:1.28-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend /app/dist /usr/share/nginx/html
EXPOSE 80
