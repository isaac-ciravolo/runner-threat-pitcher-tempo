# Frozen exploratory analysis plan

Version 1.0, frozen 2026-11-15 before any threat or pitcher-response model was fit. This is an exploratory plan, not a preregistration. The public-video timing gate remains `validation_pending`.

## Research sequence

The proposed analysis has three ordered stages. Later stages cannot be used to tune earlier labels or predictors.

1. Estimate a runner's probability of a **feed-recorded steal attempt** in an eligible first-base-only opportunity.
2. Separately estimate the probability of recorded success, conditional on a recorded attempt. Do not combine willingness to run and execution into one target.
3. Generate runner-threat predictions prospectively and estimate their predictive association with the pitcher's binary response: at least one **feed-recorded pitcher pickoff throw** before the opportunity closes.

Stage 3 is a predictive/associational recorded-action analysis. It is not an estimate of the causal effect of runner threat or of throwing over.

## Frozen opportunity and response definitions

Use the runner-control protocol v1.1 first-base-only windows without changing their denominator. A window opens before the plate appearance's first event or immediately after an event leaves first occupied and second/third empty. It closes at the next actual pitch, a state exit, or the terminal plate-appearance/half-inning boundary. Keep repeated actions, pre-first-pitch actions, runner substitutions, and windows that end without another pitch.

Every action record may belong to at most one window. Keep the following response fields distinct:

- pitcher pickoff, catcher pickoff, and unknown-initiator pickoff;
- step-off and disengagement violation;
- steal attempt and its outcome;
- pickoff outcome, including safe return, out, caught stealing, or error advance;
- no recorded pickoff/steal, which is not proof of real-world absence.

Two cached plate appearances contain a pickoff-attempt event followed by a reviewed/outcome event with the same raw disengagement ordinal. Preserve both feed records, flag the second as a continuation, and count one disengagement for rule-state reconstruction. The binary recorded-pickoff window response is unaffected.

## Predictor cutoff and feature rules

The feature cutoff is immediately before the first event for a pre-first-event window and immediately after the opening anchor otherwise. No information from a response event, the closing event's result, a later plate appearance, or a later game may enter a predictor.

Permitted opening context includes pitcher, batter and runner identity; inning and half; count and outs; score differential from the pitching team's perspective; base state; previous-pitch result when one exists; and recorded disengagements, pickoffs, step-offs, and rule resets already observed in the plate appearance. The disengagement count follows MLB's post-2023 rule: pitcher pickoffs and step-offs count, the limit resets when any runner advances, and a third unsuccessful disengagement is penalized.

Historical runner, pitcher, batter, catcher, and team features must be generated from games strictly earlier than the game being predicted. Runner threat begins with:

- prior eligible first-base-only opportunities;
- prior recorded steal attempts per eligible opportunity;
- prior recorded successes per recorded attempt;
- recency/season indicators estimated only from prior games;
- an explicit pooled-new-player value and history-availability indicator.

Shrinkage strength, preprocessing, feature selection, and any missing-value rules are learned in training data only. Final-season totals, later-game values, response-window actions, and the observed interval are prohibited. A season-level Statcast attribute such as sprint speed is optional only as a prior-season value or a reproducible as-of-game snapshot; a completed current-season value is not allowed.

Catcher identity remains missing until starting defensive alignments and every substitution are reconstructed chronologically. Do not infer the opening catcher from a final box-score lineup. The primary pitcher-pickoff model may be evaluated without a catcher term if this omission is declared in advance; catcher-adjusted or catcher-specific claims must wait.

## Broader sampling frame and chronological split

The present 211-game union is inspected development data. It combines a 30-game schedule audit with all appearances for six selected tempo-benchmark pitchers and is not league-representative or an untouched test set.

Before modeling, collect all MLB regular-season (`gameType=R`) schedules and completed public live feeds needed for:

| Role | Dates | Use |
|---|---|---|
| History only | 2022-04-07 through 2022-10-05 | Seed pre-game histories; keep the prior rule environment labeled |
| Training | 2023-03-30 through 2023-10-01 | Fit preprocessing, shrinkage, baselines, and candidate models |
| Validation | 2024-03-20 through 2024-09-30 | Select features/penalties and audit calibration; the cached subset is already inspected |
| Final test | 2025-03-18 through 2025-09-28 | Locked one-time evaluation after all choices are frozen |

Verify those bounds against the official schedule response at collection time and include every regular-season game returned, including international openers and makeup games. Assign whole games to one split; never randomly split windows or players across time. Do not download this broader frame during dataset preparation.

## Candidate models and evaluation

No model is fit in this task. After collection:

1. Fit a pooled-rate baseline and a context-only logistic baseline for recorded steal attempt.
2. Fit a regularized logistic attempt model with only the frozen, pre-cutoff features. Generate training predictions by forward/rolling origin or cross-fitting that respects game date. Generate validation predictions from training-only fits.
3. Fit the conditional-success model only among recorded attempts, using the same time discipline and reporting the much smaller denominator.
4. Freeze the threat definition and runner-model choices before fitting/comparing pitcher-response models.
5. Compare a context-only pitcher-pickoff model with the same model plus the forward-generated threat score. Do not use the threat model's in-sample fitted value for the same game.

Report opportunity and event counts, missingness, prevalence, Brier score, log loss, calibration intercept/slope and plots, discrimination, and uncertainty from whole-game resampling. Report incremental performance over simple baselines, not correlation alone. Show performance by season, disengagement count, runner-history depth, pitcher, and runner where sample sizes permit; suppress unstable individual rankings. A repeated-observation model or cluster-aware sensitivity is required before interpreting coefficients because windows repeat within games, pitchers, and runners.

The conditional-success model describes outcomes among selected attempts and must not be read as the success probability of an unobserved attempt under a different strategy. The pitcher-response coefficient is predictive association, not a causal effect.

## Secondary timing analysis

Timing remains secondary and optional. Use only explicitly labeled feed **event-start intervals** after a called ball/called strike to the same batter, with no intervening nonpitch event. Keep the action-free restriction visible: it conditions on post-threat behavior and therefore changes the population. Report terminal and action windows outside the timing denominator rather than dropping them silently.

Do not call these intervals release tempo, use them to detect small within-pitcher effects, or pass the timing gate until the frozen continuous-video protocol succeeds. The aggregate Savant match is corroboration only and the two Zac Gallen count-gap intervals remain unresolved; do not match them by guesswork.

## Readiness and stopping rules

The current table is ready for schema review, accounting checks, and collection planning. It is not ready for threat modeling because every one of its 12,228 rows lacks a complete pre-game runner history and its selection is not representative.

A recorded-pitcher-pickoff model may proceed after the complete 2022-2025 frame is collected, histories are generated forward, schedule/feed completeness checks pass, action-assignment checks pass, and all modeling choices above are frozen before the 2025 test is opened. Video validation is not a prerequisite for that action model. Timing analysis remains deferred unless its independent gate passes.

## Prior-work boundary

Loughin and Bargen already separated attempt/opportunity from success/attempt and modeled pitcher/catcher effects. Price's 2026 thesis already applies hierarchical attempt and conditional-success models to 2021-2025 data with post-2023 context including disengagements. Melville and coauthors, and Powers and coauthors, already model the strategic pitcher-runner game under the pickoff limit; Powers also uses lead-distance tracking and multilevel pickoff/steal outcome models. The Yale analysis already compares pitch mix in first-base steal situations, and Smith analyzes between-pitch time and interruption contributions.

Accordingly, this project makes no “first” or broad novelty claim. A narrower candidate contribution is a fully public, reproducible, chronologically evaluated link from forward-generated runner attempt threat to recorded pitcher pickoff response, with explicit terminal opportunities, action provenance, and measurement gates. That contribution must be re-evaluated against the full methods and references of the closest 2026 work before any SABR submission.
