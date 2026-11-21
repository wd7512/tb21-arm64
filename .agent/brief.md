# L7: CI writes each published digest and verdict back into the repo

## Problem
`.github/workflows/ci.yml`'s `task` job pushes the image it tested to `ghcr.io/wd7512/tb21-arm64/<task>:<upstream tag>` when `vars.TB21_PUBLISH == 'true'` on `main`. That variable is now set. The job ends with `# TODO: write the published digest and the verdict back into task.toml and manifest.json.`

Until that TODO is done:
- each `<task>/task.toml` still says `docker_image = "alexgshaw/<task>:<tag>"`, the upstream amd64 image;
- `manifest.json` keeps `image: null` and a hand-set `status`.

So the dataset cannot be used with hrr `images: prebuilt` on arm64.

## Change
1. **In the `task` job, after a successful push,** write `reports/ci/<task>.publish.json`:
   - `{"task", "image": "<ghcr repo>@sha256:…", "verdict", "reason", "run_url"}`;
   - the digest comes from `docker inspect --format '{{index .RepoDigests 0}}'` after the push;
   - verdict and reason come from `reports/ci/<task>.sweep.json`.

   Upload it as artifact `publish-<task>`.

   When nothing was published (a multi-arch task, or the build failed), still write the file, with `image: null`, so the verdict is recorded. In that case `docker_image` is not changed.
2. **New `tools/record_ci.py FOLDER`** (stdlib only) reads every `*.publish.json` under FOLDER. For each task:
   - **`task.toml`:** replace only the `docker_image = "…"` line with the published reference when `image` is set. Leave the rest of the file byte-for-byte unchanged.
   - **`manifest.json`:**
     - set `image` to the published reference;
     - set `status` to `verified-ci` or `failing`;
     - set `evidence` to `run_url`, or for failing tasks to `{"run": run_url, "reason": reason}`;
     - never change a `skipped` task.

     Make sure `checks/test_manifest.py`'s schema accepts these shapes, and extend it only if it must.
   - Write the manifest with the same `json.dumps(…, indent=2) + "\n"` format it already uses.
3. **New job `record`:**
   - `needs: [plan, task]`, `if: always()`, and only on `main` (push or dispatch) with `vars.TB21_PUBLISH == 'true'`;
   - `permissions: contents: write`.
   - It downloads every `publish-*` artifact into one folder and runs `tools/record_ci.py`.
   - When there is a diff, it commits as `github-actions[bot]` with the message `ci: record published images and verdicts (run <run id>)`, then pushes to `main`.
   - On a push race, retry up to 3 times with `git pull --rebase`.
   - A push made with `GITHUB_TOKEN` does not start another workflow run, so this cannot loop.
4. **Remove the TODO line.** Add one sentence to the README CI section saying CI records digests and verdicts.

## Tests
These go in `checks/test_record_ci.py`. Use real file shapes copied from this repo: a real `task.toml` (take `regex-log/task.toml`) and a manifest entry shaped like the real ones.
- A verified task gets its `docker_image` line rewritten and every other line unchanged.
- A failing task records its reason.
- `image: null` leaves `task.toml` unchanged and still records the verdict.
- A `skipped` task is untouched.

Show the first test red before the code exists, and quote the output.

## Rules
- Pin any new action to a full version tag at least two weeks old. The existing workflow uses `actions/download-artifact@v4.3.0`-style pins; match them.
- Use the stdlib only.
- The gate must pass.
- No push or `gh` commands.

## Out of scope
Pinning the four multi-arch tasks' `docker_image`, changing how images are built or tested, and any task fix.
