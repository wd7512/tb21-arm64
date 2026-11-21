# mcmc-sampling-stan

- **Class:** drift (floating CRAN dependencies), on top of the base pin. Two changes, both in `solution/solve.sh`; the tests and environment are unchanged.
- **Change 1:** `cmake` is added to the `apt-get install` list. The Dockerfile installs `r-base` with `--no-install-recommends` and no CMake.
- **Why 1:** the oracle pins Rcpp, RcppEigen, BH and StanHeaders but not RcppParallel. `StanHeaders` pulls the newest RcppParallel, now 6.2.1 (27 Aug 2026), whose `SystemRequirements` is `CMake (>= 3.5)`. The build stops with `RcppParallel requires cmake (>= 3.5); cmake was not found`, then `dependency 'RcppParallel' is not available for package 'StanHeaders'`, and rstan is never installed.
- **Change 2:** `remotes::install_version('rstan', version='2.32.7', ...)` gains `upgrade='never'`.
- **Why 2:** without it, `remotes` upgrades the pinned StanHeaders 2.32.10 to 2.39.1.1 (2 Sep 2026) as an rstan dependency. rstan loads `stanc.js` from StanHeaders, so the Stan compiler becomes the 2.39 one, which rejects the old array syntax (`int<lower=0> n[num_obs];`) that the oracle's model uses: `Ill-formed declaration. ";" expected after variable declaration`. When the upstream image was built (Oct 2025), 2.32.10 was still the newest StanHeaders, so the pin held. The oracle model is unchanged. Neither change is arm64-specific.
- **Evidence (21 Nov 2026, local arm64 Docker, Harbor 0.23.0):**
  - Unmodified solve: oracle 0.0 (`cmake was not found`).
  - Only `cmake` added: oracle 0.0, 0.0, 0.0 (`rstan version 2.32.7 (Stan version 2.39.0)`, then the old-array-syntax parse error; 3 of 6 verifier tests fail).
  - Both changes: oracle 1.0, 1.0, 1.0 (sequential), and nop 0.0.
