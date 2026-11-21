#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: tools/build.sh TASK [TAG]" >&2
    exit 2
fi

task=$1
tag=${2:-"tb21-arm64-local/${task}:dev"}
root=$(git rev-parse --show-toplevel)

if [[ "$task" == */* || ! -f "$root/$task/task.toml" ]]; then
    echo "task must be a root folder containing task.toml: $task" >&2
    exit 2
fi

cd "$root"
revision=$(git -C "$root" rev-parse HEAD)
build_args=(
    buildx build
)
if [[ "${BUILD_NETWORK:-}" == "host" ]]; then
    build_args+=(--network host)
fi
build_args+=(
    --platform linux/arm64 \
    --load \
    --tag "$tag" \
    --label "org.opencontainers.image.source=https://github.com/wd7512/tb21-arm64" \
    --label "org.opencontainers.image.revision=$revision" \
    --label "org.opencontainers.image.licenses=Apache-2.0" \
    "$task/environment"
)
docker "${build_args[@]}"
