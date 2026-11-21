# build-cython-ext

- **Class:** drift (floating dependency), on top of the base pin.
- **Change:** in `solution/solve.sh`, `pip install setuptools==80.9.0 cython==3.1.3` becomes `pip install setuptools==80.9.0 cython==3.1.3 planarity==0.6`. The pin installs before `pip install -e .`, so pyknotid's unpinned `planarity` requirement is already satisfied. The tests and environment are unchanged.
- **Why:** `pyknotid` 0.5.3 declares `planarity` without a version. planarity 1.0.0 was released on 29 Jun 2026, after the upstream image (`alexgshaw/build-cython-ext:20251031`) was built; the previous release is 0.6 (6 Jul 2024). With 1.0.0, `planarity.networkx_graph` returns nodes with no `pos` attribute, so `_construct_planar_graph` raises `KeyError: 'pos'` and the verifier's `test_pyknotid_repository_tests` (pyknotid's own suite) fails on `test_reconstructed_space_curve`. This is not arm64-specific: planarity is pure pip, and the unmodified solve fails the same way.
- **Evidence (21 Nov 2026, local arm64 Docker, Harbor 0.23.0):**
  - Unmodified solve: oracle 0.0; inside the container, pyknotid's suite gives `1 failed, 17 passed` with `KeyError: 'pos'` at `representation.py:338`, and `pip list` shows planarity 1.0.0.
  - With `planarity==0.6`: `18 passed`, then oracle 1.0, 1.0, 1.0 (sequential), and nop 0.0.
