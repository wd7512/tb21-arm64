# tb21-arm64

Native arm64 images for the 89 tasks of [Terminal-Bench 2.1](https://github.com/harbor-framework/terminal-bench-2).
The upstream task images are amd64-only. This repository builds an arm64 image for each task,
compares it with the upstream amd64 image, fixes what fails, and publishes the images at
`ghcr.io/wd7512/tb21-arm64/<task>`.

**Work in progress.** No images are published yet.

## What differs from upstream

The first commit imports the task folders unchanged. Every later change to a task is its own commit
and is described in `fixes/<task>.md`, in one of three classes:

| Class | Meaning |
| --- | --- |
| `port` | arm64 forces the change, for example an x86-only binary download. |
| `drift` | Rebuilding the upstream Dockerfile today no longer reproduces the upstream image, so the fix pins to, or copies from, that image. |
| `defect` | The task also fails on the upstream amd64 image, and is fixed here. A task fixed for a defect is not the same task as upstream, so compare its results with upstream results with care. |

## Status

A task is `verified-ci` when, on the CI arm64 runner, the oracle passes 3 sequential runs out of 3
and the `nop` agent scores 0. `manifest.json` records each task's status and evidence.

## Use with harbor-research-runner

Point the job file's task source at a commit of this repository:

```yaml
tasks:
  git:
    url: https://github.com/wd7512/tb21-arm64
    commit: <40-character commit>
  images: prebuilt
```

## Licence

Apache-2.0, as is upstream Terminal-Bench. See `NOTICE`.
