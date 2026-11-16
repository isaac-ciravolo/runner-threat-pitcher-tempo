# Code and research-process audit: G3 continuation

## Checked and corrected

- Independent model verification now reads saved prediction floats with round-trip precision, preserving near-ties in average precision. It parses ISO timestamps with optional fractional seconds explicitly. Baseline, forward and response saved-model reloads and metric recomputations pass; neither fix changes fitted model parameters.
- Future reconstruction caches now hash the driver as well as parser dependencies. The driver contains the unaffected-game migration logic, so excluding it could reuse outputs after a migration change. Cache schema 3 invalidates such reuse. New migration metadata retains its immediate source path and checksum.
- Three regression tests verify driver-change invalidation, movement-mode separation, stable signature ordering, source-preserving migration and rejection of already migrated rows. The complete suite passes 105 tests.
- The already published G3 reconstruction is unchanged. Its 60-game equivalence proof binds the exact original driver and all source dependencies; the new cache key is protection for future rebuilds. Any future migrated rebuild must satisfy the existing source-bound equivalence gate again.
- Conditional-outcome auditing retains all denominators and source checksums. The complete crosswalk revealed a missing review category, which was added transparently in a new immutable run; both runs remain available.
- Notebook outputs were executed and reviewed before their stage commits. Scientific figures show bin denominators, development status and recorded-event interpretation. Generated result bytes retain their line endings so manifest hashes survive Git checkout; SVG whitespace is treated as generated formatting.

## Limits that remain

Tests and source consistency checks do not prove measurement validity. Video annotations remain zero; feed timing is not validated release tempo. The success audit does not reconstruct full closure survival. The frozen response model cannot identify the causal value of defensive attention. The 2025 feeds remain closed, and unresolved closest-work access prevents a broad novelty claim.

Reproduce tests with `python -m unittest discover -s tests -q`, using the project's writable temporary directory on Windows. Published run manifests independently verify exact artifact bytes.
