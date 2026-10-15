# Pre-specified validation: predictions vs VIIRS burned area (VNP64A1)

Status: **specified 2026-10-15, before any VNP64A1 data was downloaded or inspected.** This is a
secondary, post-lock analysis. It does not change the v0 conclusion.

## Why

The study's labels and features both come from VIIRS active-fire (thermal) detections, so the reported
skill could partly reflect sensor behaviour rather than real fire. VNP64A1 maps **burn scars** from
changes in daily surface reflectance (char, ash, vegetation loss): a different physical signal at
500 m. It is only **partly independent**, because its algorithm also uses active-fire detections to
guide mapping. Agreement with it is necessary but not sufficient evidence of ground truth.

## Design

- **Rows:** the locked 2024 `test` and `geo_test` cell-days, scored by the locked B0 / B1 / M2 (as saved in
  `scores.parquet`). No refitting.
- **Burned-area label for (cell, D):** 1 if ≥1 VNP64A1 pixel whose centre lies in the cell has a burn date
  in **[D, D+1]**. The one-day slack is because the mapped burn date marks the first detected
  reflectance change, which can trail the fire.
- **Unknown, excluded:** cell-days where ≥50% of the cell's VNP64A1 pixels are *unmapped* in D's month.
- **Primary measure:** B1 PR-AUC against the burned-area label, compared with that label's prevalence (a
  no-skill model), with a 95% block-bootstrap CI (state × ISO week, 2,000 resamples, seed 20261015).
- **Secondary:** B1 − B0 and M2 − B1 on the burned-area label (same bootstrap). Agreement between the
  FIRMS label and the burned-area label (2×2 table, Cohen's κ). Results by state for the held-out states.

## How results will be read

- B1 lift over prevalence with CI > 0: predictions also anticipate **mapped burning**, not just thermal
  re-detection.
- Lift near zero: the study's skill may be largely specific to active-fire detection behaviour.
- Small fires and burns under canopy are often missed by 500 m burned-area mapping, so low recall
  against the FIRMS label is expected and is not by itself a model failure.

## Results (run 2026-10-15; report `reports/experiment_summaries/burned_area_validation_20261015T1036.md`)

208 VNP64A1 tiles (16 tiles × 13 granule months) were read. Of 308,713 test cell-days, 975 were excluded as ≥50% unmapped.

| 2024 set | BA prevalence | FIRMS prevalence | B1 PR-AUC vs BA | B1 lift over prevalence [95% CI] | κ (FIRMS vs BA) |
|---|---|---|---|---|---|
| test | 0.074 | 0.361 | 0.233 | **+0.160 [+0.123, +0.200]** | 0.14 |
| geo_test | 0.084 | 0.423 | 0.114 | **+0.030 [+0.006, +0.057]** | 0.08 |

- **Pre-specified reading:** the lift CI excludes 0 on both sets, so the predictions also anticipate *mapped
  burning*, not only thermal re-detection. In held-out states the effect is small.
- **The two labels agree weakly** (κ 0.08–0.14). Only 14.6% of FIRMS-positive cell-days have a mapped burn on
  D..D+1, which is expected because many small, agricultural or under-canopy fires fall below 500 m burned-area
  mapping. Odisha (forest understory fires) has the lowest BA prevalence (2.5%) and the weakest agreement
  (B1 PR-AUC 0.051); Haryāna (crop residue, 0.447) and Mizoram (shifting cultivation, 0.349) are stronger.
- B1 − B0 on the BA label: test +0.072 [+0.030, +0.113]; geo_test +0.006 [−0.016, +0.030].
- **M2 − B1 on the BA label: test −0.017 [−0.026, −0.009].** Adding weather made agreement with mapped burning
  slightly *worse*. This is consistent with the locked result that weather adds no robust value.
- Caveat: VNP64A1 uses active-fire data in its algorithm, so this is supporting, not independent, evidence.
