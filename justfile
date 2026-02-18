TAG_BASE := "ghcr.io/althingi-net"
TAG_VERSION := "latest"

_default:
    @just -u -l

_full_tag app:
    @echo "{{ TAG_BASE }}/{{ app }}:{{ TAG_VERSION }}"

# Builds all images.
build-images:
    just build-image lagasafn-base
    just build-image codex-api

# Build specific app. Options: 'lagasafn-base', 'codex-api'
build-image app:
    docker build . --no-cache -t "$(just _full_tag {{ app }})" --target "{{ app }}"

# Pushes all images to registry.
push-images:
    just push-image lagasafn-base
    just push-image codex-api

# Pushes specific app. Options: 'lagasafn-base'
push-image app:
    docker push "$(just _full_tag {{ app }})"

# Stops and cleans container images for given app.
clean-image app:
    #!/bin/bash
    set -e
    TAG="$(just _full_tag {{ app }})"
    docker container stop "$TAG" 2>/dev/null || true
    docker container rm "$TAG" 2>/dev/null || true
    docker image rm "$TAG" 2>/dev/null || true

# Runs image of given app.
run-image app:
    #!/bin/bash
    # Note: This value-hunting assumes a strict format in the `.env` file.
    SECRET_KEY="$(grep '^SECRET_KEY=' codex-api/.env | cut -d= -f2 | sed 's/^"//; s/"$//;')"
    API_ACCESS_TOKEN="$(grep '^API_ACCESS_TOKEN=' codex-api/.env | cut -d= -f2 | sed 's/^"//; s/"$//;')"
    ALLOWED_HOSTS="$(grep '^ALLOWED_HOSTS=' codex-api/.env | cut -d= -f2 | sed 's/^"//; s/"$//;')"
    docker run -it --rm \
        -e SECRET_KEY="$SECRET_KEY" \
        -e API_ACCESS_TOKEN="$API_ACCESS_TOKEN" \
        -e ALLOWED_HOSTS="$ALLOWED_HOSTS" \
        -p 8000:8000 \
        "$(just _full_tag {{ app }})"

# Runs a shell for the given app.
run-shell app:
    docker run -it --rm --entrypoint /bin/bash "$(just _full_tag {{ app }})"
