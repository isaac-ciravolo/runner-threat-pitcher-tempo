# Smallest defensible study

## Scope and estimand
Among regular-season opportunities with a runner on first and second/third empty, estimate the adjusted association between prospectively estimated recorded-steal-attempt threat and pitcher response. The long-term runner-versus-batter run trade-off is a separate, later question.

Primary timing sample: consecutive pitches to the same batter and pitcher after a called ball or called strike. Establish eligible occupancy after the preceding pitch resolves, before the response interval begins. Keep opportunities that end without a next pitch in the broader action dataset; report why they cannot contribute a completed pitch interval.

## Gate 1: literature
Read full texts, trace citations, and compare exact predictors, outcomes, eras, data access, and validation. Review the closest work before claiming novelty. A prospective threat-to-response analysis is a candidate contribution, not a verified gap.

## Gate 2: measurement
Propose roughly 30 games across early, middle, and late 2024, multiple parks and pitchers. This is an audit sample, not a power calculation.
- Cache original feeds and record source URL, retrieval time, game ID, and checksum.
- Check unique keys, event ordering, timestamp availability, duplicates, and pre-action state reconstruction.
- Preserve nonpitch actions and runner movements; distinguish pitcher pickoffs from catcher throws.
- Audit pitch-to-Statcast joins and disclose unmatched/ambiguous records.
- Manually compare approximately 100 public-video intervals, including ordinary intervals, throw-overs, step-offs, and timeouts.
- Record source video, event identifiers, observed release times, interval errors, and interruption-label agreement.
- Set an acceptable timing-error threshold before inspecting threat associations, relative to the effect size the study seeks to distinguish.
- Compare a matched aggregate sample against Savant tempo definitions where feasible.

Use “event-start interval” until release alignment is validated. If measurement fails, pivot to validated pickoff and pitch-selection outcomes. Do not discard long intervals solely because they are long.

## Gate 3: opportunity and threat definitions
Specify the event window and the exact denominator before building historical rates. Include nonattempts. Official SB/CS records do not identify every decision to run; foul-ball attempts and movement on balls in play may be missing.

Begin with a prior-season runner attempt rate per eligible opportunity, shrunk to the league rate. Use pooled estimates for sparse/new runners; estimate shrinkage using historical development data. Test a small logistic model only if it improves chronological held-out calibration.

Freeze all features at interval start. Do not use the upcoming pitch, elapsed time, or intervening defensive actions to explain that same response. Historical threat reflects historical defensive strategies, not an unattended-runner counterfactual. Keep conditional success separate; defer it until labels and the attempt model work.

## Gate 4: response analysis
Primary outcome: validated interval in seconds. Companion outcome: recorded pitcher pickoff probability per defined opportunity. Secondary outcome: pitch-family choice.

Report both total elapsed intervals and the selected subset without recorded intervening actions. A clean-interval comparison is not the effect of removing pickoffs.

Prespecify an interpretable model with pitcher effects and adjustment for count, outs, inning, score, workload, previous pitch result, batter, and catcher. Consider pitcher-game effects as a robustness check where supported. Specify repeated-observation uncertainty and report counts, missingness, exclusions, effect sizes, and confidence intervals.

Choose exact chronological development/test dates before modeling; document sample sizes and available event counts. Assess calibration and prediction gain over historical-rate/context baselines. Lock choices before evaluating later games. Avoid random pitch splits and premature individual rankings.

## Team relevance and limits
Replicable behavioral tendencies can support scouting. They cannot establish that speeding up or throwing over improves run prevention. Unobserved leads, runner intent, and selection into attempts remain confounders.

For later action comparisons, define a concrete decision (pickoff now versus pitch now), a fixed outcome window, and an identification strategy. Runs scored plus ending-state expectancy minus starting-state expectancy must use count when the window ends mid-PA. Avoid double-counting advances. Held-out prediction is not causal identification.
