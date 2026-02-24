TAG_BASE := "ghcr.io/althingi-net"
TAG_VERSION := "latest"

_default:
    @just -u -l

_full_tag app:
    @echo "{{ TAG_BASE }}/{{ app }}:{{ TAG_VERSION }}"

_sanity_check_app app:
    #!/usr/bin/env bash
    APP="{{ app }}"

    if [ "$APP" != "codex-api" ]; then
        echo "Error: Unknown app: $APP" >&2
        echo "" >&2
        echo "Known apps are:" >&2
        echo "" >&2
        echo "    codex-api" >&2
        # TODO: echo "    codex-ui" >&2
        echo "" >&2
        exit 1
    fi

_sanity_check_environment environment:
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

_establish_secret environment: (_sanity_check_environment environment)
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

# Builds specific image.
build app: (_sanity_check_app app)
    docker build .. -t "$(just deploy _full_tag {{ app }})" --target "{{ app }}"

# Builds all images.
build-all:
    just deploy build codex-api
    # TODO: just deploy build codex-ui

# Pushes specific app to container image registry.
push app: (_sanity_check_app app)
    docker push "$(just deploy _full_tag {{ app }})"

# Pushes all images to registry.
push-all:
    just deploy push codex-api
    # TODO: just deploy push codex-ui

# Stops and cleans container images for given app.
clean-image app: (_sanity_check_app app)
    #!/bin/bash
    set -e
    TAG="$(just deploy _full_tag {{ app }})"
    docker container stop "$TAG" 2>/dev/null || true
    docker container rm "$TAG" 2>/dev/null || true
    docker image rm "$TAG" 2>/dev/null || true

# Stops and cleans container images for all apps.
clean-image-all:
    just clean-image codex-api
    # TODO: just clean-image codex-ui

# Runs image of given app.
run app:
    #!/bin/bash
    SECRET_KEY="secret-string"
    API_ACCESS_TOKEN="secret-string"
    ALLOWED_HOSTS="localhost"

    docker run -it --rm \
        -e SECRET_KEY="$SECRET_KEY" \
        -e API_ACCESS_TOKEN="$API_ACCESS_TOKEN" \
        -e ALLOWED_HOSTS="$ALLOWED_HOSTS" \
        -p 8000:8000 \
        "$(just deploy _full_tag {{ app }})"

# Runs a shell for the given app.
shell app:
    docker run -it --rm --entrypoint /bin/bash "$(just deploy _full_tag {{ app }})"

# Deploys the Helm chart to a Kubernetes cluster.
deploy environment: (_sanity_check_environment environment) (_establish_secret environment)
    #!/usr/bin/env bash
    ENVIRONMENT="{{ environment }}"
    NAMESPACE="$ENVIRONMENT-althingi-net"

    helm upgrade --install lagasafn helm \
        -n "$NAMESPACE" --create-namespace \
        -f helm/values-"$ENVIRONMENT".yaml \
        --force-conflicts

# Full deployment with building and pushing of images.
full-deploy environment: (_sanity_check_environment environment)
    just deploy build-all
    just deploy push-all
    just deploy deploy {{ environment }}
