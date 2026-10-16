# Threshold calibration — `max_distance_threshold`

Source run: `eval_results/b1_v1.csv` (50 questions, 2026-10-16,
0 retries, 0 excluded rows). Regenerate with
`python scripts/calibrate_thresholds.py`.

## The two distributions

Distance is Chroma L2 (lower = closer). Each question contributes
its **minimum** retrieved distance — the single closest chunk.

- **Group A — should pass** (answerable + retrieved a gold chunk):
  n=15, min=0.331, median=0.472, mean=0.501, max=0.782
- **Group B — should fail** (unanswerable, any category):
  n=25, min=0.389, median=1.010, mean=1.024, max=1.574

Answerable questions that retrieved no gold chunk are excluded from
both groups: their label would conflate a retrieval miss with a
threshold error.

## Sweep

| threshold | TPR (A passed) | FPR (B passed) | Youden J | balanced acc |
|---|---|---|---|---|
| 0.33 | 0.000 | 0.000 | 0.000 | 0.500 |
| 0.34 | 0.133 | 0.000 | 0.133 | 0.567 |
| 0.38 | 0.267 | 0.000 | 0.267 | 0.633 |
| 0.39 | 0.267 | 0.040 | 0.227 | 0.613 |
| 0.42 | 0.267 | 0.040 | 0.227 | 0.613 |
| 0.46 | 0.400 | 0.040 | 0.360 | 0.680 |
| 0.47 | 0.400 | 0.040 | 0.360 | 0.680 |
| 0.49 | 0.533 | 0.040 | 0.493 | 0.747 |
| 0.53 | 0.667 | 0.040 | 0.627 | 0.813 |
| 0.59 | 0.733 | 0.040 | 0.693 | 0.847 |
| 0.65 | 0.800 | 0.040 | 0.760 | 0.880 |
| 0.70 | 0.867 | 0.040 | 0.827 | 0.913  ← chosen |
| 0.72 | 0.867 | 0.120 | 0.747 | 0.873 |
| 0.73 | 0.933 | 0.160 | 0.773 | 0.887 |
| 0.78 | 0.933 | 0.160 | 0.773 | 0.887 |
| 0.81 | 1.000 | 0.240 | 0.760 | 0.880 |
| 0.84 | 1.000 | 0.240 | 0.760 | 0.880 |
| 0.85 | 1.000 | 0.320 | 0.680 | 0.840 |
| 0.88 | 1.000 | 0.360 | 0.640 | 0.820 |
| 0.91 | 1.000 | 0.400 | 0.600 | 0.800 |
| 0.95 | 1.000 | 0.440 | 0.560 | 0.780 |
| 0.96 | 1.000 | 0.480 | 0.520 | 0.760 |
| 1.01 | 1.000 | 0.520 | 0.480 | 0.740 |
| 1.06 | 1.000 | 0.520 | 0.480 | 0.740 |
| 1.08 | 1.000 | 0.560 | 0.440 | 0.720 |
| 1.09 | 1.000 | 0.640 | 0.360 | 0.680 |
| 1.23 | 1.000 | 0.680 | 0.320 | 0.660 |
| 1.24 | 1.000 | 0.760 | 0.240 | 0.620 |
| 1.25 | 1.000 | 0.800 | 0.200 | 0.600 |
| 1.27 | 1.000 | 0.800 | 0.200 | 0.600 |
| 1.44 | 1.000 | 0.920 | 0.080 | 0.540 |
| 1.48 | 1.000 | 0.920 | 0.080 | 0.540 |
| 1.57 | 1.000 | 0.960 | 0.040 | 0.520 |

## Choice

- Maximise Youden J: **0.70** (J=0.827)
- Maximise balanced accuracy: 0.70 (bal=0.913)
- Previous un-calibrated default: 0.80

The two criteria agree on the integer grid point; ties are broken
toward the lower (more conservative) threshold.

## Caveat — overlap

1 of 25 unanswerable questions have a minimum distance at or below the chosen threshold (Q45). This check alone cannot refuse them; they are caught by the clinical check, by the model's own refusal, or not at all. The threshold is one layer, not the whole guard.

2 answerable gold-hitting questions (Q7, Q15) sit above the chosen threshold and would be refused by this check alone. In the v1 run they passed only because the deployed default was the un-calibrated 0.80, which also lets 6 of the 25 unanswerable questions through (see the 0.81 row of the sweep). Refusing these two is the measured cost of the calibrated threshold; it is stated here rather than hidden.

