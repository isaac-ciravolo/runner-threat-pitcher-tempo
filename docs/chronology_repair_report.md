# Chronology repair and response-stage readiness

Completed 2026-11-15 after committing the prior milestone as `dbd03f1`. The chronology defect was broader than the original 61-row quarantine: repaired histories differ in 1,253 windows across 55 games. The repair preserves all 413,081 opportunity IDs, labels, action attribution, catcher assignments and eligibility rules. Original tables and results remain unchanged; corrected data and models occupy separate paths.

## Audit and timing decisions

All 7,289 eligible 2022–2024 cached feeds were read and their SHA256 values verified against collection manifests. The audit includes 303 rescheduled, resumed or doubleheader schedule-edge games. It found 25 flagged games: 11 resumptions, 11 internal timer-violation records with reversed start/end timestamps, two final rain feeds with trailing incomplete plays, and one isolated far-future pitch timestamp. No event lacked start/end timestamps; every conservative game-freeze bound passed the 36-hour pre-pitch check.

Histories now freeze at the earliest observed event/play start, including pregame records. This deliberately withholds some otherwise usable same-day information and is not claimed to be first-pitch or release time. All resumed innings retain the original game's freeze. Availability normally uses the latest observed event/play timestamp as a conservative completed-play proxy, with explicit exceptions in `docs/chronology_timing_dispositions.md`.

Game 716404 is restored at its original-day event cutoff; final history availability is delayed to October 5, 04:00 UTC. The cached final feed contains only eight innings. The official disposition date is documented by [MLB](https://www.mlb.com/amp/news/marlins-mets-suspended-game-will-not-be-played.html). Its retrospective final-feed population is not all physical actions before the ruling.

For two rain-ending games, availability is buffered 24 hours after the final rain advisory. That is an assumption, not measured completion. Game 745520 contains one April pitch stamped in September; the repair does not invent a timestamp and conservatively withholds that game's history until September. Reversed internal timer-violation intervals remain flagged and are not used as durations. These qualifications limit claims about exact live availability, but preserve a documented conservative replay. Final feeds cannot prove when later corrections first became public.

## History changes

| Season | Windows preserved | Changed history rows | Largest absolute prior-opportunity change |
| --- | ---: | ---: | ---: |
| 2022 | 137,732 | 495 | 19 |
| 2023 | 138,862 | 337 | 20 |
| 2024 | 136,487 | 421 | 164 |

Fifty of the restored game's 61 rows have changed histories. The largest correction is in a long-suspended 2024 game. Using only a completion-before-header check would not have caught such cases: a resumption header can precede final completion while still being too late for original-game predictions.

History construction reuses the audited eligibility rules and separate rule-era count blocks, ordered by corrected freeze and released only when availability is strictly earlier. Independent batch summation over 34 games (all resumptions and special cases plus a seeded sample) verifies 5,364 runner-history equalities. Full-table checks cover unique IDs, nonnegative counts, regime decomposition, constant within-game histories and zero post-rule histories in 2022. Protected original columns compare identically by opportunity ID.

## Refit and handoff

The original threat model and training-only calibration adoption rule were rerun without tuning on 2024. The selected policy remains identity: on the corrected late-2023 selection population, raw log loss is 0.071355 versus calibrated 0.071402, while Brier is 0.015936 versus 0.015858. Calibration improves Brier but fails the joint adoption rule.

There are now 211,818 scored training windows: 72,956 in 2022 and all 138,862 in 2023. All 61 formerly quarantined rows are restored; 54 windows move into the warmup period because their conservative freeze precedes July 1. Month-boundary and diagnostic populations therefore differ from v1; their metrics are not a strictly matched before/after performance comparison.

On the identical 136,487-window 2024 population, the raw model has log loss 0.076797, Brier 0.017221 and AP 0.087252. Mean absolute prediction change from v1 is 0.0000131; maximum change is 0.006406. For 211,757 commonly scored training windows, mean absolute change is 0.0000172 and maximum is 0.060666. These small aggregate changes do not excuse the temporal defect; the corrected pipeline is the required handoff.

Every saved monthly model/calibrator bundle reproduces its exported scores, and the final bundle reproduces all development predictions. Calibration and subgroup tables reconcile counts and attempts. `notebooks/08_chronology_repair.ipynb` executes verification in a fresh IPython process. The full repository suite has 42 passing tests. 2025 remains unopened; no response model was fit during this repair stage.

## Reproduction

Run from the repository root. The audit reads existing cached feeds and makes no network requests. The rebuild reuses existing opportunity tables and does not reparse window definitions.

```powershell
python -m scripts.chronology_audit
python -m scripts.chronology_edge_evidence
python -m scripts.chronology_dispositions
python -m scripts.rebuild_chronology_histories
python -m scripts.forward_threat_v2
python -m scripts.verify_chronology_repair
python scripts/execute_forward_threat_notebook.py notebooks/08_chronology_repair.ipynb
$env:TEMP = (Resolve-Path data/processed/test_tmp).Path
$env:TMP = $env:TEMP
python -m unittest discover -s tests -q
```

The audit and history rebuild each take several minutes. Existing source manifests and feeds are required; no fresh collection was performed. Do not overwrite the original historical tables to run the corrected models.

- `docs/chronology_repair_protocol.md` and `docs/chronology_timing_dispositions.md`: frozen audit and explicit dispositions.
- `results/chronology_repair/`: all-game audit, schedule-edge review, 12 anomalous event records, dispositions, per-game history changes, prediction comparisons, hashes and verification.
- `data/processed/chronology_repair/`: ignored corrected opportunity tables with separate original timestamp, freeze, last-event and availability fields.
- `results/forward_threat_v2/` and `data/processed/forward_threat_v2/`: compact corrected results and ignored reloadable models/keyed scores.
- `docs/pitcher_response_protocol.md`: frozen context-only versus context-plus-threat design, dependence sensitivities, label audit and final-test boundaries.

The response-stage protocol uses 2023 for primary response fitting under the current disengagement rule, preserving 2022 for threat/history construction. The response-stage gate is satisfied for a qualified retrospective recorded-action analysis, not an exact live-feed or causal claim. A separate final-test policy and measurement/literature work remain necessary before 2025 or team-strategy recommendations.
