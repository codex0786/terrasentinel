# Uttarakhand: ground-reported incidents vs VIIRS detections — 2026-10-15 10:49 UTC

Secondary validation of *detections* (not day-level predictions). Ground data: Uttarakhand Forest Department division-wise bulletin snapshot `uk_forest/daily_fire_report_division/b3/b37f2446247069ec749f8efeac5234b3132259a6d3018dd7f3275b79b25feb29.html` (retrieved 2026-10-15T10:46 UTC), 2026 season 15 Feb – 15 Oct. Satellite: qualifying VIIRS S-NPP + NOAA-20 detections (SP to 30 Jun, NRT after), same period, assigned to geoBoundaries ADM2 districts.

- Ground total: 600 incidents, 548.8 ha, across 41 divisions → 13 districts
- Satellite total in Uttarakhand: 10,923 detections

## Rank correlations (Spearman, 20,000-permutation p-values; n = 13 districts)

| set                                | ground    | satellite      |   spearman_rho |   perm_p_two_sided |   n_districts |
|:-----------------------------------|:----------|:---------------|---------------:|-------------------:|--------------:|
| all divisions                      | incidents | detections     |          0.473 |              0.106 |            13 |
| all divisions                      | incidents | detection_days |          0.195 |              0.516 |            13 |
| all divisions                      | incidents | frp_sum        |          0.517 |              0.073 |            13 |
| all divisions                      | area_ha   | detections     |          0.511 |              0.08  |            13 |
| all divisions                      | area_ha   | detection_days |          0.258 |              0.396 |            13 |
| all divisions                      | area_ha   | frp_sum        |          0.538 |              0.061 |            13 |
| excluding multi-district divisions | incidents | detections     |          0.529 |              0.067 |            13 |
| excluding multi-district divisions | incidents | detection_days |          0.22  |              0.468 |            13 |
| excluding multi-district divisions | incidents | frp_sum        |          0.562 |              0.051 |            13 |
| excluding multi-district divisions | area_ha   | detections     |          0.512 |              0.077 |            13 |
| excluding multi-district divisions | area_ha   | detection_days |          0.239 |              0.422 |            13 |
| excluding multi-district divisions | area_ha   | frp_sum        |          0.523 |              0.07  |            13 |

## District table (all divisions)

| region            |   incidents |   area_ha |   detections |   frp_sum |   detection_days |
|:------------------|------------:|----------:|-------------:|----------:|-----------------:|
| Chamoli           |         185 |     138.5 |         1388 |    5626.6 |               74 |
| Garhwal           |          76 |     120.7 |         1859 |    5995.8 |               81 |
| Dehradun          |          64 |      78.7 |          362 |    1315.3 |               65 |
| Uttarkashi        |          58 |      38.4 |          653 |    3169   |               66 |
| Tehri Garhwal     |          58 |      51.5 |         1341 |    5106.3 |               89 |
| Pithoragarh       |          44 |      35.8 |          782 |    2186.8 |               70 |
| Rudraprayag       |          40 |      27.1 |          470 |    1738.4 |               58 |
| Nainital          |          27 |      28.2 |          841 |    3044.4 |               87 |
| Almora            |          22 |      12.3 |         1570 |    5155.5 |               90 |
| Champawat         |          11 |      10.3 |          394 |     856.8 |               43 |
| Bageshwar         |          10 |       5.3 |          659 |    2049.2 |               67 |
| Udham Singh Nagar |           5 |       2   |          523 |    3394.1 |               82 |
| Hardwar           |           0 |       0   |           81 |     323.1 |               38 |

Caveats: one season, 13 units; the division→district mapping is approximate (see config); ground incidents count forest-department-recorded fires on forest land only, while satellite detections include agricultural and non-forest fires.
