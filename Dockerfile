FROM python:3.12-slim AS builder
ARG NODE_VERSION=24.14.0
ARG NODE_ARCH=linux-x64

# Build dependencies: codex-api
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    # Required for codex-api.
    git g++ python3-dev \
    # Required for installing Node.
    curl xz-utils \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-${NODE_ARCH}.tar.xz \
    | tar -xJ -C /usr/local --strip-components=1

# Build: codex-api
RUN pip install --upgrade pip
COPY requirements-freeze.txt /build/codex-api/requirements-freeze.txt
RUN pip install --prefix=/build/codex-api/python-packages -r /build/codex-api/requirements-freeze.txt

# Build: codex-ui
COPY codex-ui/ /build/codex-ui/
WORKDIR /build/codex-ui/
RUN npm install
RUN npm run build

FROM python:3.12-slim AS codex-api

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    gettext git libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/codex-api/python-packages /usr/local

RUN mkdir -p /app/codex-api

COPY lagasafn/ /app/lagasafn
COPY codex-api/ /app/codex-api
COPY data /app/data

WORKDIR /app/codex-api

RUN SECRET_KEY=unused \
    API_ACCESS_TOKEN=unused \
    ALLOWED_HOSTS=unused \
    python3 manage.py collectstatic --noinput

RUN SECRET_KEY=unused \
    API_ACCESS_TOKEN=unused \
    ALLOWED_HOSTS=unused \
    python3 manage.py compilemessages

ENTRYPOINT ["daphne", "-b", "0.0.0.0", "-p", "8000", "mechlaw.asgi:application"]


FROM nginx:stable-alpine AS codex-ui
COPY --from=builder /build/codex-ui/.output/public/ /usr/share/nginx/html/
COPY entrypoint.codex-ui.sh /docker-entrypoint.d/40-runtime-config.sh
RUN chmod +x /docker-entrypoint.d/40-runtime-config.sh
