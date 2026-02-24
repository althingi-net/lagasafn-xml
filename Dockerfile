FROM python:3.12-slim AS codex-api

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    g++ python3-dev gettext git \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/codex-api

COPY lagasafn/ /app/lagasafn
COPY codex-api/ /app/codex-api
COPY data /app/data
COPY requirements-freeze.txt /app/requirements-freeze.txt

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install -r requirements-freeze.txt

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
