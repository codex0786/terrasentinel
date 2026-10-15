# fire_persistence_v0: baselines (2026-10-14 20:34 UTC)

Test sets scored: **no (development run)**

## Rows per set

| set                |   size |    sum |     mean |
|:-------------------|-------:|-------:|---------:|
| embargo            |  11920 |   4040 | 0.338926 |
| geo_test           |  29058 |   (withheld) |  (withheld) |
| geo_train_excluded | 109472 |  52308 | 0.477821 |
| geo_val            |  41095 |  19027 | 0.463    |
| test               | 279655 |   (withheld) |  (withheld) |
| train              | 834795 | 326046 | 0.39057  |
| val                | 293844 | 107976 | 0.36746  |

## Metrics

| model             |      n |   prevalence |   pr_auc |   roc_auc |   brier |    ece |   top10%_precision |   top10%_recall |   top10%_false_alerts_per_day |   fixed100_precision |   fixed100_recall |   fixed100_false_alerts_per_day |   fixed100_flagged_frac | fixed100_saturated   | eval_set   |
|:------------------|-------:|-------------:|---------:|----------:|--------:|-------:|-------------------:|----------------:|------------------------------:|---------------------:|------------------:|--------------------------------:|------------------------:|:---------------------|:-----------|
| B_null_prevalence | 293844 |       0.3675 |   0.3675 |    0.5    |  0.233  | 0.0231 |             0.2692 |          0.0737 |                       61.3665 |               0.2507 |            0.0761 |                         69.7188 |                  0.1115 | False                | val        |
| B0_seasonal       | 293844 |       0.3675 |   0.6901 |    0.786  |  0.1802 | 0.0459 |             0.7896 |          0.2161 |                       17.6705 |               0.6665 |            0.2022 |                         31.0284 |                  0.1115 | False                | val        |
| B1_satellite_only | 293844 |       0.3675 |   0.7129 |    0.7995 |  0.1707 | 0.0173 |             0.8284 |          0.2268 |                       14.4119 |               0.6905 |            0.2095 |                         28.7983 |                  0.1115 | False                | val        |
| B_null_prevalence |  41095 |       0.463  |   0.463  |    0.5    |  0.2539 | 0.0724 |             0.3792 |          0.085  |                        7.6725 |               0.4104 |            0.477  |                         37.7884 |                  0.5381 | True                 | geo_val    |
| B0_seasonal       |  41095 |       0.463  |   0.7034 |    0.7359 |  0.2167 | 0.0966 |             0.8377 |          0.1877 |                        2.0058 |               0.4904 |            0.5699 |                         32.6609 |                  0.5381 | True                 | geo_val    |
| B1_satellite_only |  41095 |       0.463  |   0.758  |    0.7801 |  0.1923 | 0.0446 |             0.8717 |          0.1954 |                        1.5855 |               0.5036 |            0.5853 |                         31.8145 |                  0.5381 | True                 | geo_val    |

## B1 vs B0 (block bootstrap, region x ISO week)

| eval_set   | comparison       |   diff |   ci_low |   ci_high |   n_boot_used |   n_blocks |
|:-----------|:-----------------|-------:|---------:|----------:|--------------:|-----------:|
| val        | B1 - B0 (pr_auc) | 0.0228 |   0.0115 |    0.034  |          2000 |       1331 |
| geo_val    | B1 - B0 (pr_auc) | 0.0546 |   0.0308 |    0.0751 |          2000 |        137 |

## B1 coefficients (standardised log1p features)

|                      |    coef |
|:---------------------|--------:|
| fire_count_1d        |  0.1071 |
| fire_count_3d        |  0.3408 |
| fire_count_7d        |  0.9052 |
| fire_count_30d       |  0.2629 |
| frp_sum_1d           |  0.0216 |
| frp_sum_7d           | -0.2908 |
| days_since_last_fire | -0.1831 |

Labels are future *detections*, not verified fire (see docs/limitations.md).
