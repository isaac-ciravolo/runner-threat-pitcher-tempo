# Corrected forward threat scores

Run `027eb6c0e93d4836a07dac5900a3708f` preserves the frozen monthly training schedule and calibration-selection rule. It scores 71,517 windows in 2022 and all 135,536 in 2023; 63,455 early-2022 warmup windows intentionally have no prediction. Every monthly training/calibration pool precedes its prediction period under conservative game-availability timestamps.

The July–October 2023 selection rule chooses logistic recalibration: log loss 0.093255 versus 0.093342 raw, and Brier 0.020041 versus 0.020189. The paired 200-game-bootstrap interval for the selection log-loss difference crosses zero (-0.000310 to 0.000117); the rule uses point estimates and this is not proof of a significant selection-period improvement. Average precision is slightly lower after pooling monthly recalibrated scores.

The fixed training-fitted recalibration improves 2024 development log loss from 0.100407 to 0.100029 and Brier from 0.021770 to 0.021639. The paired whole-game bootstrap interval for calibrated-minus-raw log loss is -0.000487 to -0.000231. Calibration slope improves from 0.822650 to 0.957339, though the highest occupied bin remains overconfident. Average precision stays 0.062232, as expected for a single monotonic recalibration.

Independent verification reloads 340,156 predictions from all 12 monthly bundles and the final bundle, and recomputes 24 metrics. The verifier explicitly parses ISO timestamps with optional fractional seconds and preserves serialized prediction floats. Notebook 12 and the exported calibration figure were reviewed. No response-stage specification changes follow these results; the primary response analysis retains raw forward threat, with calibrated threat as the frozen sensitivity. 2025 remains closed.
