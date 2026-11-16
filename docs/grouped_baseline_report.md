# Corrected recorded-attempt baseline

Run `1a46c4a2ee9b44d6901f6e197448659d` fits the frozen specifications on 270,508 windows from 2022–2023 and evaluates 133,103 windows from 2024, with 2,994 recorded attempts (2.2494%). The artifact split name `heldout_2024` is historical: 2024 is development data, not the untouched final test.

| Model | Development log loss | Brier score | Average precision |
|---|---:|---:|---:|
| Training prevalence | 0.107897 | 0.022000 | 0.022494 |
| Opening context | 0.105222 | 0.021826 | 0.046040 |
| Context + separate runner histories | 0.100407 | 0.021770 | 0.062232 |

The separate-history specification reduces log loss relative to context by approximately 4.58%. Its 200 whole-game bootstrap interval for log loss is 0.097202–0.103434; the paired difference versus training prevalence is -0.008435 to -0.006623. This interval does not test the context-versus-history contrast. Calibration slope is 0.822650, and the highest occupied history bin predicts 26.2% while observing about 11.4%. Report this overconfidence alongside discrimination improvements. These are recorded-feed predictive associations.

All 24 independently recomputed metrics and 532,412 reloaded model predictions pass. The initial verifier discrepancy was caused by default CSV float parsing breaking near-ties in average precision; round-trip prediction parsing restores the saved values without relaxing tolerances or changing model results. Notebook 11 and the exported calibration figure were executed and reviewed. The 102-test suite passes. No choices were tuned on 2024 and 2025 remains closed.

Reproduce with `python -m scripts.grouped_models baseline`, then `python -m scripts.verify_grouped_models baseline`, notebook 11 and `python -m scripts.plot_grouped_calibration baseline`.
