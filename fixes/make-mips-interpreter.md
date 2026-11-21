# make-mips-interpreter

- **Class:** drift (dead download).
- **Change:** in `environment/Dockerfile`, `RUN curl https://distro.ibiblio.org/slitaz/sources/packages/d/doom1.wad > doom.wad` becomes `COPY doom.wad /app/doom.wad`, and `environment/doom.wad` is vendored. The path is the same one the curl wrote to (the WORKDIR is `/app`). The solution and tests are unchanged; the canary line is kept. the same fix applies to make-doom-for-mips.
- **Why:** the URL now returns 404 (upstream terminal-bench-2-1 #246). Curl is run without `-f`, so the upstream build would write the 341-byte error page into `doom.wad`. On arm64 the build instead stops at that step with curl exit code 60. Either way the image cannot be rebuilt from the original Dockerfile.
- **The file:** `doom1.wad`, the id Software shareware v1.9 data file, 4196020 bytes, vendored unmodified (id's shareware licence allows unmodified redistribution; see `NOTICE`). sha256 `1d7d43be501e67d927e415e0b8f3e29c3bf33075e859721816f652a526cac771`. Source: `DOOM1.WAD` inside https://archive.org/download/DoomsharewareEpisode/doom.ZIP, byte-identical to https://github.com/Akbar30Bill/DOOM_wads/raw/master/doom1.wad. No amd64 image was pulled, emulated or read.
- **Hash check:** the hash recorded from the upstream image's `/app/doom.wad` during the earlier Isambard harvest could not be found in the private repository (the harvest script takes it from a hash file that was never committed), so this file is not yet checked against it. It does equal the well-known hash of the v1.9 shareware file.
- **Evidence (21 Nov 2026, local arm64 Docker, Harbor 0.23.0):**
  - The unmodified Dockerfile: the build fails at the curl step (exit code 60), so the oracle run ends in a RuntimeError (no reward).
  - The fixed rebuild: oracle 1.0, 1.0, 1.0 (sequential), and nop 0.0. No frame-rendering timeout occurred.
