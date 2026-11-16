# Pitcher-response protocol v1 (frozen before response-model fitting)

Frozen 2026-11-15. This is exploratory development, not preregistration. No response model has been fit. Execution requires the chronology-v2 audit, history reconstruction, forward-score checks and reviewed evidence report to pass first. Any remaining timing ambiguity must have an explicit exclusion or conservative availability disposition; no automatic promotion from a final-feed status.

## Question and estimand

Does prospectively estimated recorded-steal-attempt threat improve prediction of at least one feed-recorded pitcher pickoff within a frozen first-base-only opportunity, beyond opening context and pitcher/catcher identity? This is incremental predictive association under observed strategies, not a causal response to threat, an optimal pickoff policy or runs prevented. The threat score includes context itself: improvement cannot be attributed solely to runner history.

## Population, target and time ordering

Use the chronology-v2 opportunity table with original v1.1 window IDs and action accounting. Predict immediately before the first PA event or after the opening anchor. Close at the next pitch, state exit or terminal boundary. Primary response fitting uses all 2023 windows with a verified forward raw threat score; 2022 supplies threat-model/history warmup but is a distinct rule regime, not primary response training. Evaluate on all eligible 2024 windows, with threat scores from a fit using 2022–2023 data only. Keep terminal, runner-change, repeated-action and nonattempt windows. Report exact unavailable-score and chronology exclusions. 2024 is previously inspected development data; 2025 stays closed.

Label = recorded_pitcher_pickoff_indicator. Catcher-only and unknown-initiator pickoffs are not labeled pitcher pickoffs. Report their counts; a prespecified sensitivity omits unknown-initiator windows, explicitly recognizing that this changes the population using response information. Do not use any response-window action, steal outcome, closing result, terminal flag or identity-change flag as a predictor. Opening pitcher/catcher identity describes the opportunity at cutoff, not necessarily the actor after a substitution.

## Fixed models

Fit pooled training prevalence for reference, then two matched L2 logistic models (C=1, lbfgs, max_iter=2000, no class weights). Use the same rows, preprocessing and regularization in both:

1. Context: inning, half inning, opening balls/strikes/outs, opening-timing category, opening recorded disengagement count/reset count/remaining allowance, opening pitcher ID and chronologically assigned catcher ID.
2. Context plus raw forward threat, represented as logit of probability clipped to [1e-8,1-1e-8]. Preserve raw probability in all exported records and explanations.

Fit numeric median imputation plus missing indicators and standardization on training only. Missing categorical values use MISSING; one-hot encoding ignores unseen levels. Report unseen pitcher/catcher rates. Omit score, handedness, pitch characteristics and previous-pitch results in this first response baseline; their omission limits interpretation. No penalty/feature search. Calibration is identity for the response models.

Primary threat is the raw chronology-v2 score regardless of the candidate recalibration's 2024 performance. One declared sensitivity replaces it with the genuinely prospective calibrated score (with its documented fallback); 2024 uses the training-fitted candidate map. Another matched sensitivity adds pre/post runner-history log exposure and zero-history indicators to both context models to assess whether exposure depth explains incremental prediction. Do not select among sensitivities using 2024.

## Chronological diagnostic and evaluation

Before full response refit, fit on 2023 games whose chronology-v2 availability precedes July 1 UTC and evaluate games freezing July 1 onward. Exclude crossing games from that diagnostic fit only. Then refit on all 2023 games available before January 1, 2024 and score 2024 once under these choices. No 2024 calibration fit is applied. Training threat scores must remain their own earlier-origin predictions; no replacement by full-fit threat scores.

Report row/game/event flow by year and diagnostic partition; positive counts/rates; log loss (primary metric), Brier and AP; paired metric differences; descriptive calibration intercept/slope and fixed probability bins [0,.005,.01,.02,.05,.1,.2,1]. Report observation and event counts for opening disengagement count, runner-history depth, terminal and runner-change audits, and unseen identities. Omit unstable individual rankings. No coefficient interpretation in this initial report.

Use 500 paired whole-game bootstrap resamples (seed 20261115) for 95% percentile intervals of incremental metrics. Repeat metric-difference resampling by opening pitcher and separately by opening runner as dependence sensitivities; these are not a full crossed-cluster model and do not include fitting uncertainty. Explain disagreement among uncertainty estimates. Report negative findings; primary success is evidence of incremental log-loss improvement with a paired game interval below zero, not mere nonzero correlation. Secondary metrics and calibration may contradict it and must remain visible.

## Validation and measurement gates

Assert one-to-one score joins, identical comparison populations, strictly earlier base-fit and calibrator availability, and unchanged frozen response labels. Test that modifying future/response fields cannot alter X. Verify reloadable fitted artifacts and prediction accounting. Save environment, source hashes, specification hash, model bundles, keyed predictions, executed notebook, tables and decision log. Review notebook output before commit.

Prepare a seeded stratified video queue for positive pitcher-pickoff labels and apparent negatives, covering pre-first-event, terminal, catcher/unknown-initiator and interruption cases. Record selection probabilities; do not infer overall sensitivity/specificity from a convenience sample or treat inaccessible video as a verified negative. Actual manual/video annotation remains required before real-world action-completeness claims. Timing/tempo remains behind the separate video gate.

Before SABR submission or any novelty statement, compare full methods and references of the closest literature recorded in the source/claim ledger. Before 2025, freeze the entire response/threat pipeline, primary hypothesis, metrics, sensitivities, history updates and final refit rules in a separate final-test policy. This protocol does not unlock 2025. Expected-run and conditional-success work remain later stages.
