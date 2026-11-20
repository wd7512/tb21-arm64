#!/bin/bash
#SBATCH --job-name=tb21-sweep
#SBATCH --time=12:00:00
#SBATCH --output=tb21-sweep-%j.out
# Build and test tb21-arm64 tasks inside one Slurm allocation, using the rootless Docker setup
# from harbor-research-runner's scripts/slurm/docker-engine.sh.
#
# Submit from a checkout of this repository, adding your site's account and partition flags:
#   sbatch [site flags] tools/slurm-sweep.sbatch [TASK...]
# With no TASK, every task in manifest.json is swept. Rows go to SWEEP_OUT as they finish; a
# task that already has a row is skipped, so resubmitting with the same SWEEP_OUT resumes.
#
# Optional environment:
#   UV              uv executable, with uvx beside it (default: uv on PATH)
#   SWEEP_JOBS      tasks at a time (default 2)
#   SWEEP_OUT       results folder on persistent storage (default reports/local/slurm/<job id>)
#   HRR_REF         harbor-research-runner ref that provides docker-engine.sh (default dev)
#   BUILDX_VERSION  buildx CLI plugin release (default 0.38.2)
#   HRR_ENGINE, HRR_DOCKER_VERSION, HRR_COMPOSE_VERSION are read by docker-engine.sh.

# engine_selected, ensure_compose_plugin and stop_docker_engine come from docker-engine.sh.
# shellcheck disable=SC2154,SC2329

set -eu
umask 077

repo=$(git -C "${SLURM_SUBMIT_DIR:-.}" rev-parse --show-toplevel)
out=${SWEEP_OUT:-$repo/reports/local/slurm/${SLURM_JOB_ID:-manual}}
uv_bin=${UV:-$(command -v uv)}
buildx_version=${BUILDX_VERSION:-0.38.2}
mkdir -p "$out"
work=$(mktemp -d /tmp/tb21-sweep.XXXXXX)
log="$out/engine.log"

cleanup() {
    docker system prune --all --force >/dev/null 2>&1 || true
    stop_docker_engine 2>/dev/null || true
    rm -rf "$work" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM

git -C "$repo" rev-parse HEAD >"$out/revision"
git clone --quiet --filter=blob:none https://github.com/wd7512/harbor-research-runner "$work/hrr"
git -C "$work/hrr" checkout --quiet "${HRR_REF:-dev}"
# shellcheck source=/dev/null
. "$work/hrr/scripts/slurm/docker-engine.sh"
if ! start_docker_engine; then
    printf 'no Docker API or Compose plugin on this node; see %s\n' "$log" >&2
    exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
    export DOCKER_CONFIG="${DOCKER_CONFIG:-$work/docker-config}"
    mkdir -p "$DOCKER_CONFIG/cli-plugins"
    case "$(uname -m)" in
        aarch64 | arm64) arch=arm64 ;;
        x86_64) arch=amd64 ;;
        *) arch=$(uname -m) ;;
    esac
    curl -fsSL --retry 2 --max-time 180 \
        "https://github.com/docker/buildx/releases/download/v$buildx_version/buildx-v$buildx_version.linux-$arch" \
        -o "$DOCKER_CONFIG/cli-plugins/docker-buildx"
    chmod 700 "$DOCKER_CONFIG/cli-plugins/docker-buildx"
    ensure_compose_plugin
fi
{
    printf 'engine=%s\n' "$engine_selected"
    docker version --format 'docker={{.Server.Version}}'
    docker compose version --short | sed 's/^/compose=/'
    docker buildx version | sed 's/^/buildx=/'
    "$uv_bin" --version | sed 's/^/uv=/'
} >"$out/versions"

uv_dir=$(dirname "$uv_bin")
export PATH="$uv_dir:$PATH"
export UV_CACHE_DIR="$work/uv-cache" UV_PYTHON_INSTALL_DIR="$work/uv-python"
cd "$repo"
set +e
"$uv_bin" run python tools/sweep.py --jobs "${SWEEP_JOBS:-2}" --prune \
    --out "$out" --jobs-dir "$work/jobs" "$@"
status=$?
set -e
tar -czf "$out/jobs-${SLURM_JOB_ID:-manual}.tar.gz" -C "$work" jobs 2>/dev/null || true
exit "$status"
