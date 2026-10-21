# 两个产物：
#   target=app  后端镜像（api 和 worker 共用，靠 command 区分）
#   target=web  Caddy + 前端静态文件
# 国内服务器拉不到 PyPI / npm 时，用 --build-arg PIP_INDEX_URL=… / NPM_REGISTRY=… 换镜像源

FROM node:20-alpine AS web-build
ARG NPM_REGISTRY=https://registry.npmjs.org/
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --registry "$NPM_REGISTRY"
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS app
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV TZ=Asia/Shanghai PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 \
    UV_INDEX_URL=${PIP_INDEX_URL} PATH=/app/.venv/bin:$PATH
RUN pip install --no-cache-dir --index-url "$PIP_INDEX_URL" uv==0.12.23
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY data/questions ./data/questions
COPY data/raw/trial ./data/raw/trial
RUN mkdir -p data/raw/daily
CMD ["uvicorn", "app.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

FROM caddy:2.10-alpine AS web
ENV TZ=Asia/Shanghai
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=web-build /web/dist /srv/web
