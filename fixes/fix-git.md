# fix-git

- **Class:** drift (dead download).
- **Change:** `environment/setup.sh` clones `https://github.com/AI-Harness-Evals/personal-site.git` instead of `https://github.com/TheMikeMerrill/personal-site.git`, which now asks for credentials, so the image no longer builds.
- **Source of the mirror:** recovered from the upstream image `alexgshaw/fix-git:20260403` (`master` at `19b5d101aa7083ae47a3a033ccadac79b0693488`). The same change is the only one in [AI-Harness-Evals/terminal-bench-2-1-native](https://github.com/AI-Harness-Evals/terminal-bench-2-1-native).
- **Evidence:** `tools/compare.py` on the arm64 build against `alexgshaw/fix-git@sha256:389b9c82…` (20 Nov 2026): all 116 files under `/app/personal-site` are present, and the working-tree files are identical. Only `.git` internals differ: the clone's pack files, the index and reflogs, and the one commit that `setup.sh` creates at build time with the current timestamp. Any rebuild of the upstream image differs in the same way.
