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
    docker build . -t "$(just _full_tag {{ app }})" --target "{{ app }}"

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

    # Make sure that 'localhost' is allowed when running in this way.
    ALLOWED_HOSTS="$ALLOWED_HOSTS,localhost"

    docker run -it --rm \
        -e SECRET_KEY="$SECRET_KEY" \
        -e API_ACCESS_TOKEN="$API_ACCESS_TOKEN" \
        -e ALLOWED_HOSTS="$ALLOWED_HOSTS" \
        -p 8000:8000 \
        "$(just _full_tag {{ app }})"

# Runs a shell for the given app.
run-shell app:
    docker run -it --rm --entrypoint /bin/bash "$(just _full_tag {{ app }})"

_sanity_check environment:
    #!/usr/bin/env bash
    ENVIRONMENT="{{ environment }}"

    if [ "$ENVIRONMENT" != "prod" ] && [ "$ENVIRONMENT" != "staging" ]; then
        echo "Error: Unknown environment: $ENVIRONMENT" >&2
        echo "" >&2
        echo "Applicable environments are:" >&2
        echo "" >&2
        echo "    prod" >&2
        echo "    staging" >&2
        echo "" >&2
        exit 1
    fi

_establish_secret environment:
    #!/usr/bin/env bash
    ENVIRONMENT="{{ environment }}"
    NAMESPACE="$ENVIRONMENT-althingi-net"

    # We expect to find the string "NotFound" if secrets don't already exist,
    # because merely relying on the exit code would confuse that situation with
    # any other error that might possibly come up.
    NOT_FOUND=$(kubectl -n "$NAMESPACE" get secret env-secret 2>&1 | grep NotFound | wc -l)

    if [ "$NOT_FOUND" != "0" ]; then
        # There are no secrets. We must create them.

        # It doesn't matter what they are, as long as they are secret and don't
        # get updated every time the Helm chart is upgraded. We will generate
        # random ones, which can be updated manually later in K8s if needed.
        SECRET_KEY="$(openssl rand -hex 20)"
        API_ACCESS_TOKEN="$(openssl rand -hex 20)"

        kubectl -n "$NAMESPACE" create secret generic env-secret \
            --from-literal=SECRET_KEY="$SECRET_KEY" \
            --from-literal=API_ACCESS_TOKEN="$API_ACCESS_TOKEN"
    fi

# Deploys the Helm chart to a Kubernetes cluster.
deploy environment: (_sanity_check environment)
    #!/usr/bin/env bash
    ENVIRONMENT="{{ environment }}"
    NAMESPACE="$ENVIRONMENT-althingi-net"

    just _establish_secret "$ENVIRONMENT"

    helm upgrade --install lagasafn deployment/helm \
        -n "$NAMESPACE" --create-namespace \
        -f deployment/helm/values-"$ENVIRONMENT".yaml \
        --force-conflicts
