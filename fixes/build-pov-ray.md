# build-pov-ray

- **Class:** drift (a pinned apt version left the archive), on top of the base pin.
- **Change:** in `solution/solve.sh`, the apt install line `wget=1.21.4-1ubuntu4.1` becomes `wget`. The tests and environment are unchanged.
- **Why:** Ubuntu noble now serves only `wget 1.21.4-1ubuntu4.5` (noble-updates and noble-security) and `1.21.4-1ubuntu4` (noble); `4.1` was superseded and removed. `apt-get install wget=1.21.4-1ubuntu4.1` fails with `E: Version '1.21.4-1ubuntu4.1' for 'wget' was not found`, `set -e` is not reached because `which gcc` fails first, and `build-essential` is never installed. This is not arm64-specific: the archive no longer carries that version for any architecture. I removed the pin instead of moving it to `4.5`, because the environment `Dockerfile` already installs `wget` and `4.5` would be dropped from the archive at the next security update, so a new pin would break again. `ncompress=5.0-1` is still available and stays pinned.
- **Evidence (21 Nov 2026, local arm64 Docker, Harbor 0.23.0):**
  - Unmodified solve: oracle 0.0 (`E: Version '1.21.4-1ubuntu4.1' for 'wget' was not found`, then `ERROR: gcc not found`).
  - With the pin removed: oracle 1.0, 1.0, 1.0 (sequential), and nop 0.0.
