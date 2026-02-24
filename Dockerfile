FROM python:3.12-slim AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    g++ python3-dev \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
COPY requirements-freeze.txt /requirements-freeze.txt
RUN pip install --prefix=/install -r /requirements-freeze.txt

FROM python:3.12-slim AS codex-api

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    gettext git libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

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
