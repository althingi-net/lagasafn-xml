# Image 1: The base image containing the library and data.
FROM debian:trixie AS lagasafn-base

# Install required Debian packages.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      python3-venv build-essential python3-dev \
 && rm -rf /var/lib/apt/lists/*

# Copy needed code.
RUN mkdir -p /app/lagasafn
COPY lagasafn/ /app/lagasafn
COPY requirements-freeze.txt /app

# Copy needed data.
RUN mkdir -p /app/data
COPY data/ /app/data

# Setup Python environment.
RUN python3 -m venv /venv

# Install required Python packages.
RUN /venv/bin/pip install -r /app/requirements-freeze.txt

# Image 2: Build the `codex-api` app.
FROM lagasafn-base AS codex-api

RUN mkdir -p /app/codex-api
COPY codex-api/ /app/codex-api

WORKDIR /app/codex-api
ENTRYPOINT ["/venv/bin/python3", "manage.py", "runserver", "0.0.0.0:8000"]
