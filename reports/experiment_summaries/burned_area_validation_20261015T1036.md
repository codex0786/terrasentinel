# Burned-area validation (VNP64A1) — 2026-10-15 10:36 UTC

Pre-specified in `docs/validation_burned_area.md`; secondary, post-lock.

- VNP64A1 tiles read: 208; burned cell-days: 105,054
- 2024 test cell-days: 308,713; excluded as ≥50% unmapped: 975; analysed: 307,738

## Primary

| set      |   cell_days |   ba_prevalence |   firms_prevalence |   B0_pr_auc_vs_BA |   B1_pr_auc_vs_BA |   M2_pr_auc_vs_BA |   B1_lift_over_prev | lift_ci          |   top10_precision_vs_BA |   kappa_FIRMS_vs_BA |
|:---------|------------:|----------------:|-------------------:|------------------:|------------------:|------------------:|--------------------:|:-----------------|------------------------:|--------------------:|
| geo_test |       28938 |          0.0836 |             0.4232 |            0.1076 |            0.1136 |            0.1094 |              0.0301 | [+0.006, +0.057] |                  0.1161 |              0.0787 |
| test     |      278800 |          0.0738 |             0.361  |            0.1611 |            0.2333 |            0.216  |              0.1595 | [+0.123, +0.200] |                  0.2545 |              0.1412 |

## Model comparisons on the burned-area label

| set      | comparison             |    diff | ci                 |
|:---------|:-----------------------|--------:|:-------------------|
| geo_test | B1 - B0 (PR-AUC vs BA) |  0.006  | [-0.0162, +0.0301] |
| geo_test | M2 - B1 (PR-AUC vs BA) | -0.0042 | [-0.0126, +0.0058] |
| test     | B1 - B0 (PR-AUC vs BA) |  0.0722 | [+0.0303, +0.1126] |
| test     | M2 - B1 (PR-AUC vs BA) | -0.0173 | [-0.0261, -0.0091] |

## Agreement: FIRMS label vs burned-area label (cell-days)

|   FIRMS next-day detection |      0 |     1 |
|---------------------------:|-------:|------:|
|                          0 | 188315 |  6531 |
|                          1 |  96439 | 16453 |

## Held-out states

| cell_region   |   cell_days |   ba_prev |   B1_pr_auc_vs_BA |
|:--------------|------------:|----------:|------------------:|
| Haryāna       |        6569 |    0.2291 |            0.4468 |
| Mizoram       |        2534 |    0.1642 |            0.3494 |
| Odisha        |       19835 |    0.0251 |            0.0505 |

