TAG_BASE := "ghcr.io/althingi-net"

_default:
    @just -u -l

# Builds all images.
build-images:
    just build-image lagasafn-base

# Build specific app. Options: 'lagasafn-base'
build-image app:
    #!/bin/bash
    set -e
    TAG="{{ TAG_BASE }}/{{ app }}:latest"
    docker build . --no-cache -t "$TAG"
    docker push "$TAG"

# Pushes all images to registry.
push-images:
    just push-image lagasafn-base

# Pushes specific app. Options: 'lagasafn-base'
push-image app:
    #!/bin/bash
    set -e
    TAG="{{ TAG_BASE }}/{{ app }}:latest"
    docker push "$TAG"
