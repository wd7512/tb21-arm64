# L4: CI that builds and tests task images on GitHub arm64 runners

## Problem
A task is `verified-ci` when the oracle passes 3 sequential runs out of 3 and nop scores 0 **on the CI arm64 runner** (`README.md`, "Status"). There is no CI. The repo is public at `wd7512/tb21-arm64`, so `ubuntu-24.04-arm` runners are free; up to 20 jobs run at once.

`tools/sweep.py TASK --out DIR` already does everything for one task:
- it builds with `tools/build.sh`, or pulls the upstream arm64 image for the four multi-arch tasks;
- it runs `tools/test_task.py` (oracle ×3, then nop);
- it writes `DIR/<task>.sweep.json`, `.test.json` and `.log`, with Harbor job folders in `DIR/jobs`.

CI must call it, one task per job, and must not reimplement it.

## Change
1. **`tools/ci_tasks.py`** (stdlib only) prints the JSON list of tasks for a matrix.
   - `--all`: every task in `manifest.json` whose status is not `skipped`. The skipped status lands in a parallel lane, so treat a missing status value as not skipped.
   - `--changed BASE`: task folders touched by `git diff --name-only BASE...HEAD`, intersected with the manifest and excluding skipped ones. If none changed but anything under `tools/`, `manifest.json`, `pyproject.toml` or `.github/` changed, print the canary set `["break-filter-js-from-html", "mteb-retrieve", "regex-log"]`.
   - The git call goes through an injectable `run`.
   - Add tests in `checks/test_ci_tasks.py` covering: task change, tools-only change, docs-only change (empty list), skipped task excluded, unknown folder ignored.
2. **`.github/workflows/ci.yml`:**
   - **`gate` job** (`ubuntu-24.04-arm`): `astral-sh/setup-uv` pinned to a full version tag, then `uv sync --locked`, then the gate command read from `pyproject.toml` (`[tool.devtools.delegate].gate_command`), run unpiped.
   - **`plan` job:** on `pull_request` it runs `ci_tasks.py --changed origin/${{ github.base_ref }}` (checkout with `fetch-depth: 0`); on `push` to main it diffs against `github.event.before`; on `workflow_dispatch` with input `all: true` it runs `--all`.
   - **`task` job:** a matrix over plan's output, `fail-fast: false`, `max-parallel: 20`, `timeout-minutes: 240`, on `ubuntu-24.04-arm`. Steps:
     1. free disk by removing preinstalled toolchains (`/usr/share/dotnet`, `/usr/local/lib/android`, `/opt/ghc`, `/opt/hostedtoolcache/CodeQL`) and run `docker system prune -af`; print `df -h /` before and after;
     2. set up uv;
     3. `uv run python tools/sweep.py "${{ matrix.task }}" --out reports/ci`;
     4. always upload `reports/ci/*.json` and `reports/ci/*.log` as artifact `task-<task>`;
     5. fail the job when the verdict is not `verified`, which is sweep's exit code.
   - **`publish` job:** only on `push` to `main`, only when `vars.TB21_PUBLISH == 'true'`, and only for tasks whose `task` job passed.
     - Permissions: `packages: write`.
     - It logs in to `ghcr.io` with `GITHUB_TOKEN`, rebuilds nothing, and pushes the image the task job built.
     - Each task job therefore saves its built image with `docker save` as an artifact only when publishing is enabled. If that is too large, the publish job may rebuild with `tools/build.sh`, as long as the digest it pushes comes from that build. Choose one, explain the choice, and keep it simple.
     - The tag is `ghcr.io/wd7512/tb21-arm64/<task>:<upstream tag>`, the upstream tag being the part after `:` in `manifest.json` `upstream.image`.
     - Skip the four multi-arch tasks, whose image is upstream's.
     - Writing digests back into `task.toml` and `manifest.json` is **out of scope**; leave a `TODO` line in the workflow.
   - Concurrency: `group: ci-${{ github.ref }}`, with `cancel-in-progress` true for pull requests only.
3. **`README.md`:** a short "CI" section covering what runs on a PR, on main, and on dispatch, and that publishing is off until the owner sets the repository variable `TB21_PUBLISH=true`.

## Rules
- Pin every action to a full version tag (for example `actions/checkout@v5.0.0`) that is at least two weeks old.
- No secrets except `GITHUB_TOKEN`.
- No push or `gh` commands.
- Use the stdlib only.
- The gate must pass.
- `actionlint` is not available; keep the YAML plain.

## Out of scope
Writing digests back, updating the manifest status from CI results, an amd64 runner, and any task fix.
