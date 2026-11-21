# protein-assembly

- **Class:** drift (a live API renamed a field), on top of the base pin.
- **Change:** in `solution/solve.sh`, the `pdb_ids.py` helper `get_single_fasta` filters RCSB features with `feat.get("type") != "modified_monomer"`; it is now `!= "non_standard_monomer"`. The tests and environment are unchanged.
- **Why:** the oracle fetches each sequence from `https://data.rcsb.org/rest/v1/core/polymer_entity/<ID>/1` and uses the chromophore's parent residues to replace the unresolved `X` in mCherry (2H5Q, position 71, parents MET, TYR, GLY) and Clover (5WJ2, position 87, parents GLY, TYR, GLY). RCSB now reports these features with `type: "non_standard_monomer"`; the `additional_properties` (`PARENT_COMP_ID`) and positions are unchanged. With the old name nothing matched, the `X` stayed in the fusion, and `dnachisel` ended in `NoSolutionError` (`EnforceTranslation`, wrong translation at 324-327 and 1611-1614). This is not arm64-specific, and it explains why the oracle also fails on the amd64 image. The "remove leading methionines" block stays: the verifier's expected sequences have no leading M. The oracle needs live network access to RCSB, PubChem and FPbase.
- **Evidence (21 Nov 2026, local arm64 Docker, Harbor 0.23.0):**
  - Unmodified solve: oracle 0.0 (`NoSolutionError`; `sequences.csv` still shows `X` for 2H5Q and 5WJ2).
  - With the renamed type: oracle 1.0, 1.0, 1.0 (sequential), and nop 0.0.
