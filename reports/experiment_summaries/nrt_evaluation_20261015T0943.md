# B1 on near-real-time data — 2026-10-15 09:43 UTC

Secondary, post-lock analysis (not pre-registered). Labels are final NRT detections; features use a 3 h publication lag. Unobserved days excluded: ['2026-08-03'].

| set                                 |   days |   cell_days |   prevalence |   B1_pr_auc |   lift_over_prevalence | lift_ci          |   top10_precision |   brier |
|:------------------------------------|-------:|------------:|-------------:|------------:|-----------------------:|:-----------------|------------------:|--------:|
| NRT 2026-08-01..2026-10-14          |     74 |       10570 |       0.3344 |      0.7491 |                 0.4147 | [+0.373, +0.445] |            0.7936 |  0.143  |
| SP 2024 test 2024-08-01..2024-10-14 |     74 |        7316 |       0.3276 |      0.6639 |                 0.3362 | [+0.283, +0.378] |            0.7231 |  0.1634 |

## By month

|   month |   ('cell_days', 'NRT 2026') |   ('cell_days', 'SP 2024') |   ('prevalence', 'NRT 2026') |   ('prevalence', 'SP 2024') |   ('B1_pr_auc', 'NRT 2026') |   ('B1_pr_auc', 'SP 2024') |
|--------:|----------------------------:|---------------------------:|-----------------------------:|----------------------------:|----------------------------:|---------------------------:|
|       8 |                        1961 |                       1323 |                        0.19  |                       0.192 |                       0.47  |                      0.442 |
|       9 |                        4106 |                       3054 |                        0.348 |                       0.316 |                       0.714 |                      0.624 |
|      10 |                        4503 |                       2939 |                        0.385 |                       0.401 |                       0.832 |                      0.76  |

Lift = B1 PR-AUC − prevalence (PR-AUC of a no-skill model), 95% block-bootstrap CI.
Differences between rows mix product (NRT vs SP), lag, and year; they are descriptive.
