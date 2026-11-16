# Corrected recorded pitcher-pickoff response

Run `b2820b3352964af2a1209119a6521136` tests the frozen response specifications on G3 completed-play opportunities. Training uses 135,536 windows from 2,430 games in 2023, with 7,479 recorded pitcher-pickoff windows. Development evaluation uses 133,103 windows from 2,429 games in 2024, with 7,635 positive windows (5.7362%). The threat models and histories use earlier-game availability; no 2025 feeds were opened.

Adding raw forward threat improves development log loss by **4.58%** relative to context alone. This supports incremental prediction of recorded pitcher pickoffs under observed strategies. The score contains context as well as runner history; the gain cannot be attributed solely to runner identity or interpreted as a causal response to threat.

| Primary model | Log loss | Brier | Average precision |
|---|---:|---:|---:|
| Training prevalence | 0.219690 | 0.054076 | 0.057362 |
| Opening context and pitcher/catcher identities | 0.218756 | 0.053963 | 0.079788 |
| Context plus raw forward threat | 0.208741 | 0.053008 | 0.119551 |

The primary paired log-loss difference is -0.010015. Its 500-resample 95% percentile interval is -0.010970 to -0.009082 when resampling games, -0.011092 to -0.008993 by opening pitcher, and -0.011958 to -0.007896 by opening runner. Game-resampled differences also favor threat for Brier (-0.000955; interval -0.001164 to -0.000749) and average precision (+0.039763; interval +0.036492 to +0.043638). These separate one-way dependence checks hold fitted models fixed; they do not include training uncertainty or provide joint crossed-cluster inference.

## Prespecified sensitivities

| Variant | Log-loss difference, augmented minus context | Game-bootstrap 95% interval |
|---|---:|---:|
| Raw threat, primary | -0.010015 | [-0.010970, -0.009082] |
| Prospectively calibrated threat | -0.009939 | [-0.010856, -0.009044] |
| History exposure added to both models | -0.008572 | [-0.009491, -0.007663] |
| Omit windows containing unknown initiators | -0.009551 | [-0.010535, -0.008623] |

Pitcher- and runner-resampled intervals are also below zero for every listed log-loss comparison. The exposure adjustment reduces the incremental gain. The unknown-initiator sensitivity removes nine 2024 windows based on response information and changes the population; it is not a replacement primary analysis. No variant was selected based on 2024 performance. In the earlier 2023 diagnostic, raw threat reduced log loss from 0.205936 to 0.195473 on 67,223 windows.

## Calibration, population and interpretation

Response calibration remains imperfect. The augmented model predicts 5.5994% overall versus 5.7362% observed, with calibration intercept -0.627738 and slope 0.746470. Its highest occupied bin predicts 28.21% versus 18.01% observed (3,903 windows). The plot includes bin denominators; good aggregate discrimination does not justify calibrated individual risk claims.

Retain all 527 terminal windows, 2,532 runner-change windows, nine unknown-initiator windows and 381 windows containing catcher pickoffs in the primary population. These flags can overlap. Terminal windows include 415 recorded pitcher-pickoff positives; terminal status is determined after opening and is never a predictor or prospective selection rule. Descriptive terminal subgroup rates must not be treated as opening-time calibration targets. There are 22,811 windows with unseen pitchers and 8,818 with unseen catchers; one-hot preprocessing handles these without future fitting.

The old 4.16% response gain belongs to an invalid prediction boundary and remains withdrawn. The corrected 4.58% result uses different boundaries and recovered labels, so their difference does not isolate the effect of one repair. The 2024 sample is inspected development data, not a pristine final test. Feed consistency is not independent action-completeness validation; genuine video annotations remain zero. No release-tempo, optimal-action, run-prevention or novelty claim follows.

## Verification

All 24 split/variant/model comparisons and 72 bootstrap rows pass publication accounting. Independent verification reloads all 16 fitted response bundles (1,602,582 scored predictions) and reproduces 72 metrics. Notebook 13 was executed and reviewed; the calibration PNG/SVG was visually inspected. The complete code suite passes 105 tests. Immutable manifests bind the inputs, model bundles, predictions, environment and frozen specifications.

Reproduce with `python -m scripts.grouped_models response`, `python -m scripts.verify_grouped_models response`, notebook 13 and `python -m scripts.plot_grouped_calibration response`. The next research gate is independent video annotation and completion of the closest-work review. Conditional-success and expected-run fitting remain deferred under the repair amendment; 2025 remains closed.
