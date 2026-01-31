# Image 1: The base image containing the `lagasafn-xml` library and data.
FROM debian:trixie AS lagasafn-xml

# Install required Debian packages.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3-venv build-essential python3-dev \
 && rm -rf /var/lib/apt/lists/*

# Copy needed data.
RUN mkdir -p /app
COPY lagasafn /app
COPY requirements-freeze.txt /app
COPY data /app

# Setup Python environment.
RUN python3 -m venv /venv

# Install required Python packages.
RUN /venv/bin/pip install -r /app/requirements-freeze.txt

WORKDIR /app/codex-api
ENTRYPOINT ["python3", "manage.py"]
