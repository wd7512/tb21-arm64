# Agent instructions: tb21-arm64

This repository holds the 89 Terminal-Bench 2.1 task folders, patched where needed, so that each one
runs from a native arm64 image published at `ghcr.io/wd7512/tb21-arm64/<task>`.

## Layout

- `<task>/`: one Harbor task folder per task, at the repository root, because hrr reads a git
  task source as `<repo>/<task>`. These folders are benchmark content: change one only for a fix
  that is recorded in `fixes/<task>.md`, or, for a base image pin, in `fixes/base-pins.md`.
- `fixes/<task>.md`: for each task changed beyond its base pin, what changed, why, the class and the evidence.
- `fixes/base-pins.md`: one table of every base image pin (old and new `FROM`, match quality, evidence).
- `manifest.json`: for each task, the upstream package and image, our image digest and the status.
- `tools/`: scripts that compare, build and test images.
- `checks/`: pytest tests for `tools/` and for repository invariants.

## Fix classes

- `port`: arm64 forces the change (for example, an x86-only binary download).
- `drift`: rebuilding the upstream Dockerfile today no longer gives the upstream image (a floating
  base image or package, or a dead download). Fixed by pinning to, or copying from, the upstream
  amd64 image.
- `defect`: the task fails on the upstream amd64 image as well.

## Status

A task is `verified-ci` when, on the CI arm64 runner, the oracle passes 3 sequential runs out of 3
and the `nop` agent scores 0. `verified-isambard` adds the same result on Isambard-AI. Otherwise it is
`failing`, and its reason is recorded.

## Rules

- uv for Python; Harbor 0.23.0 (the version hrr pins).
- Keep the canary GUID lines in task files.
- Never push images or tags from a local machine; only the CI workflow publishes.
- Tests are fast and few, and guard a real failure.
- Every image must be native `linux/arm64`; never build from, copy from, or run an amd64 image, let `tools/test_task.py` enforce the architecture, and keep the two QEMU tasks skipped.
