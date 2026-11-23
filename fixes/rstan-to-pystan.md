# rstan-to-pystan

- **Class:** port. One change, in `solution/solve.sh`; the tests, instruction and environment are unchanged.
- **Change:** after `make -C /tmp/httpstan`, on `aarch64` only, the oracle replaces `httpstan/stanc` with stanc3
  v2.35.0's `linux-arm64-stanc` release asset.
- **Why:** httpstan 4.13.0's Makefile pins `STANC_VERSION := 2.35.0` but always downloads `linux-stanc`, the
  x86-64 binary. On arm64 every model build fails inside httpstan with
  `OSError: [Errno 8] Exec format error: .../httpstan/stanc`; pystan then fails to parse the error response
  (`ValueError: TAPE_ERROR`), no estimates are written, and the verifier fails on missing `/app/alpha_est.csv`.
  The replacement is the same compiler version built for arm64.
- **Hidden locally:** Docker Desktop on macOS runs amd64 binaries through emulation, so the unmodified oracle
  passes there (1.0, 23 Nov 2026). Hosts without amd64 emulation (the GitHub arm64 runner, Neoverse HPC nodes) fail.
- **Evidence (23 Nov 2026):**
  - Unmodified, GitHub arm64 runner (run 45151497267): oracle 0.0, 0.0, 0.0, each with the exec format error above.
  - With the change: this pull request's CI run (oracle 3 of 3, nop 0).
