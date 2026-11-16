# Literature review and originality boundary

Checked 2026-11-15. This is a targeted review for freezing the exploratory design, not a systematic-review claim. Bibliographic/abstract and publicly accessible method descriptions were checked for the closest work; full reference tracing and full-text comparison remain required before a SABR submission.

## Closest prior work

| Source | Population and method | Relevance to this project | Boundary / required response |
|---|---|---|---|
| [Loughin & Bargen (2008), *Assessing pitcher and catcher influences on base stealing in MLB*](https://pubmed.ncbi.nlm.nih.gov/17852677/) | First innings, 1978-1990; more than 48,000 first-only opportunities and 9,000 attempts; separate mixed-effects logistic models for attempt/opportunity and success/attempt, with pitcher and catcher random effects. | Establishes the two-stage denominator and repeated-player precedent. | The attempt/success separation and pitcher/catcher effects are not novel here. Their first-inning, older-rule population differs from the proposed post-2023 full-game frame. |
| [Price (2026), *Running the Numbers*](https://dash.harvard.edu/entities/publication/69bbabbc-7b57-4fd4-b179-39b2cd164fa7) | 2021-2025 event data plus Statcast attributes; hierarchical logistic attempt and conditional-success models; context includes count, outs, inning, score differential, disengagements, sprint speed, and pitch flight time. | Very close modern overlap in population, outcomes, contextual predictors, and post-2023 focus. | Blocks any claim that modern two-stage steal modeling with disengagement context is new. Exact opportunity construction, predictor timing, validation, and full references must be compared from the thesis before submission. |
| [Powers et al. (2026), *Strategies under a pickoff limit in baseball*](https://arxiv.org/abs/2601.15608) | Zero-sum sequential runner/pitcher game; optical lead-distance data; generalized linear mixed models for pickoff and stolen-base outcome probabilities using lead, context, and player skill. | Directly models the pickoff-limit interaction and pitcher response with information unavailable in public feeds. | Closest strategic overlap. This project cannot claim a first model of pickoff behavior under the limit and cannot reproduce lead-distance results from public data. |
| [Melville et al., *The Pitcher's Dilemma*](https://www.sloansportsconference.com/research-papers/the-pitchers-dilemma-a-game-theoretical-model-of-pickoffs-and-stolen-bases) | Extensive-form game with equilibrium pickoff, steal, pitchout, and hit-and-run strategies under the 2023 rules. | Shows that pickoff/steal decisions are jointly strategic rather than isolated binary outcomes. | A predictive association in public feed data is not an equilibrium estimate or a causal recommendation. |
| [Bogaty, Duncan & Benz (2017), *Effect of Baserunners on MLB Pitch Selection*](https://sports.sites.yale.edu/effect-baserunners-mlb-pitch-selection) | Descriptive 2016 PitchF/x analysis; compares pitch-family shares by base state, then first-only situations and a five-runner speed subset. | Precedent for pitch-choice response to apparent steal situations and runner speed. | Descriptive grouping does not supply a prospective individual threat score, chronological evaluation, or action model. Pitch-selection analysis remains outside the present task. |
| [Smith (2019), *Time Between Pitches: Cause of Long Games?*](https://sabr.org/journal/article/time-between-pitches-cause-of-long-games/) | Timing study of the 2018 season and sources of delay between pitches, including throws by pitchers/catchers. | Establishes that interruptions materially contribute to between-pitch time and must not be hidden. | Timing definitions/populations differ; the present feed `startTime` is still not independently validated as release time. |

## Measurement and rule sources

- [MLB's disengagement glossary](https://www.mlb.com/glossary/rules/balk) states that pitcher pickoff attempts and step-offs count toward a two-disengagement plate-appearance limit, that the limit resets when a runner advances, and that a third unsuccessful attempt is penalized. Mound visits and timeouts do not count. This rule controls the opening-state reconstruction.
- [Baseball Savant's pitch-tempo leaderboard](https://baseballsavant.mlb.com/leaderboard/pitch-tempo) is the aggregate timing benchmark already audited. Its near-exact action-free aggregate match is corroboration, not independent release validation.
- [Baseball Savant's sprint-speed leaderboard](https://baseballsavant.mlb.com/leaderboard/sprint_speed) defines a season-level running metric. A completed current-season value would contain later-season information for earlier opportunities, so the exploratory plan permits only prior-season values or reproducible as-of-game snapshots.

## Design implications

The literature supports four frozen choices:

1. Model recorded attempt/opportunity separately from recorded success/attempt.
2. Treat player and game context as repeated, time-varying information rather than independent rows.
3. Generate the runner-threat score strictly forward in time before relating it to pitcher response.
4. Keep recorded pickoff response, strategic prescription, event-start timing, and causal effects as separate claims.

Price and Powers make broad novelty language especially untenable. A potentially distinguishable contribution is narrower: a public-data-only, fully reproducible opportunity/action dataset that retains terminal nonattempts, freezes predictor cutoffs, generates runner threat prospectively, and evaluates incremental prediction of a recorded pitcher pickoff on a later season. That is only a candidate contribution. It must survive full-text comparison, reference chaining, and chronological held-out evaluation.

## Claims not supported by this review

- This is not the first attempt/success, pickoff, runner-threat, or post-2023 disengagement model.
- Failure to find an identical public-data implementation would not prove originality.
- Predicting a pickoff does not show that a throw is optimal or that threat caused the throw.
- Statcast lead-distance work cannot be replicated or contradicted with the present public feed fields.
- No prior source validates the feed event-start field as an individual pitch-release timestamp.
