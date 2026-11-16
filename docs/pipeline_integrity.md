# Pipeline integrity and completed runs

The code-audit fixes change validation, publication and provenance; they do not change frozen statistical definitions, model hyperparameters, calibration selection or prediction windows.

## Source snapshots

Before rebuilding histories, `validate_source_snapshot` requires matching game coverage and per-game SHA256 values across opportunity rows, the chronology audit, timing dispositions and eligible collection manifests. It rejects duplicate IDs, missing hashes, stale rows, modified audited time bounds, season mismatches and history availability earlier than the last audited event. New input hashes are still recorded for provenance; recording a hash is not a substitute for validating it.

## Publishing forward-model runs

`forward_threat.main()` uses local configuration and returns `RunPaths(results, local)`. Defaults are never mutated, including after a failed call. Both the original and chronology-v2 entry points use this workflow:

1. Write to private `.staging/<run_id>` directories under the two output roots.
2. Validate score accounting, probabilities, monthly temporal order, readable model bundles, policy consistency and required deliverables.
3. Hash every artifact and move the completed directories to `runs/<run_id>`. Run directories have unique names and are not overwritten.
4. Atomically replace `current_run.json` in the result root. This single completion pointer publishes the paired result/model directories.

If fitting, validation, directory movement or pointer replacement fails, the previous pointer and completed artifacts remain available. A failure between directory moves can leave an unreferenced run directory, but readers cannot mistake it for the current run. Staging and orphan directories are retained for diagnosis; the pipeline does not automatically delete prior work. This is process-interruption protection, not a claim about storage durability under hardware failure.

Read a completed run once at the start of an operation:

```python
from scripts.artifact_runs import resolve_run
from scripts.recorded_attempt_baseline import ROOT

run = resolve_run(
    ROOT / "results/forward_threat_v2",
    ROOT / "data/processed/forward_threat_v2",
)
# run.results / "metrics.csv"
# run.local / "training_forward_scores.csv.gz"
```

The resolver checks the pointer, completion manifest and every artifact hash. Invalid pointers or modified artifacts fail explicitly; they do not silently fall back. Pre-existing committed snapshots remain readable when there is no pointer and the legacy provenance and final model bundle exist. Those legacy files are preserved, not overwritten or retroactively assigned a new completion manifest. Once a pointer exists, consumers must use the resolver rather than read flat legacy filenames. The verification script and notebooks have been updated accordingly.

Chronology-v2 provenance extensions are assembled before publication, not patched into a completed run afterward. Commit reviewed compact artifacts from the directory referenced by the pointer along with that pointer; the model directory remains ignored as before.

## Runtime checks and environment

Production validation in the baseline, chronology audit/disposition/rebuild, forward pipeline and handoff verifier uses explicit `ValidationError` exceptions. Python optimization cannot remove these checks. Assertions in tests and notebook QA remain assertions.

Each forward run records current Python, pandas, NumPy and scikit-learn versions. Historical baseline versions are retained separately as `baseline_environment` lineage and cannot masquerade as the current environment.

## Verification

Run from the repository root:

```powershell
New-Item -ItemType Directory -Force data/processed/test_tmp | Out-Null
$env:TEMP = (Resolve-Path data/processed/test_tmp).Path
$env:TMP = $env:TEMP
python -m unittest discover -s tests -q
```

Regression tests cover source mismatches, duplicate/missing games, modified timing bounds, repeated calls, failed fits, staged validation failure, interruption between directory moves, failure before pointer replacement, artifact tampering, legacy reads, current-environment capture, and a real input-hash check executed under `python -O`.

## Completed regression check

All 62 repository tests pass. The source-snapshot validator accepts all 413,081 existing opportunity rows against the audited feeds, dispositions and eligible manifests. A full chronology-v2 forward run was executed under `data/processed/audit_fix_validation/`, using the new staging, validation, manifest and completion-pointer workflow. Its 276,594-row training score file (211,818 scored rows), 136,487 development predictions, selected calibration policy and seven compact CSV tables match the prior run exactly. Current environment metadata was verified independently. Original research outputs were not replaced. The validation run and detailed verification JSON remain ignored local artifacts.

## Corrected completed-play pipeline

The grouped reconstruction uses separate G2 opportunity IDs and immutable run roots. Raw responses are independently checked against event order and explicit action links before history construction. Opening pitcher identities use ordered substitutions. History verification compares incremental counts with independent batch sums over games whose information was available strictly before the prediction game's cutoff.

The baseline, forward and response entry points reuse the frozen statistical specifications with verified grouped inputs. Response fitting requires the forward run's input hashes to match its own opportunity hashes; matching IDs alone is insufficient. Result publication checks complete model/partition coverage and bootstrap output. A separate verifier reloads model bundles and recomputes metrics from saved keyed predictions. Code hashes and input/run manifests identify each handoff.

Commands from the repository root, in order:

```powershell
python -m scripts.rebuild_grouped_events --full --workers 8
python -m scripts.grouped_histories
python -m scripts.execute_forward_threat_notebook notebooks/10_grouped_reconstruction.ipynb
python -m scripts.grouped_models baseline
python -m scripts.verify_grouped_models baseline
python -m scripts.grouped_models forward
python -m scripts.verify_grouped_models forward
python -m scripts.grouped_models response
python -m scripts.verify_grouped_models response
```

Audit and commit each completed stage before proceeding. The implementation audit passes 86 tests, including stale input/score snapshots, strictly earlier history availability, retrospective action links and duplicated response assignment. Full-run findings are reported separately only after execution. These checks do not establish independent action completeness, release-time measurement, novelty or causal identification.
