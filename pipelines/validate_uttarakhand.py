"""Compare ground-reported forest-fire incidents (Uttarakhand Forest Department, 2026 season to date)
with VIIRS detections, by district. Validates *detections*, not day-level predictions.

Inputs: the archived division-wise bulletin snapshot, configs/uttarakhand_divisions.yaml (written before
any comparison), geoBoundaries ADM2, VIIRS SP (to 2026-06-30) and NRT (from 2026-07-01) detections.

    python pipelines/validate_uttarakhand.py
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from terrasentinel.config import REPO_ROOT, data_dir
from terrasentinel.geospatial.boundary import assign_regions
from terrasentinel.ingestion.archive import RawArchive
from terrasentinel.labels.persistence import filter_qualifying
from terrasentinel.validation.firms_schema import normalize_firms, read_firms_csv

SEASON = (pd.Timestamp("2026-02-15", tz="UTC"), pd.Timestamp("2026-10-15", tz="UTC"))
UK_BBOX = "77.5,28.6,81.2,31.6"
N_PERM, SEED = 20000, 20261015


def spearman_perm(x: np.ndarray, y: np.ndarray, rng) -> tuple[float, float]:
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    rho = float(np.corrcoef(rx, ry)[0, 1])
    null = np.array([np.corrcoef(rx, rng.permutation(ry))[0, 1] for _ in range(N_PERM)])
    return rho, float((np.abs(null) >= abs(rho)).mean())


def main() -> None:
    archive = RawArchive(data_dir() / "raw")
    snap = max((r for r in archive.records() if r.product == "daily_fire_report_division"),
               key=lambda r: r.retrieved_at_utc)
    table = pd.read_html(io.StringIO(archive.read(snap).decode("utf-8", "replace")))[0]
    total_row = table[table["Division"].str.contains("Grand Total", na=False)].iloc[0]
    div = table[table["SNO"].notna()].copy()
    assert div["Total Incidents"].sum() == total_row["Total Incidents"], "division rows do not sum to the total"

    mapping = yaml.safe_load((REPO_ROOT / "configs" / "uttarakhand_divisions.yaml").read_text())["divisions"]
    unmapped = sorted(set(div["Division"]) - set(mapping))
    if unmapped:
        raise SystemExit(f"Divisions missing from the mapping: {unmapped}")
    div["district"] = div["Division"].map(lambda d: mapping[d]["district"])
    div["multi"] = div["Division"].map(lambda d: bool(mapping[d].get("multi", False)))

    adm2_path = next(archive.root / r.path for r in archive.records() if r.product == "IND_ADM2")
    adm1 = next(archive.root / r.path for r in archive.records() if r.product == "IND_ADM1")
    state = gpd.read_file(adm1)
    uk_poly = state[state["shapeName"].str.startswith("Uttar") & state["shapeName"].str.contains("kh")].geometry.iloc[0]
    adm2 = gpd.read_file(adm2_path).to_crs("EPSG:4326")
    adm2 = adm2[adm2.representative_point().within(uk_poly)]   # names repeat nationally, not within a state
    if adm2["shapeName"].duplicated().any() or len(adm2) != 13:
        raise SystemExit(f"expected 13 unique Uttarakhand districts, got {sorted(adm2['shapeName'])}")
    districts = adm2[["shapeName", "geometry"]].rename(columns={"shapeName": "region"}).reset_index(drop=True)

    # Detections: SP (Uttarakhand envelope) to 2026-06-30, NRT afterwards.
    frames = []
    for r in archive.records():
        q = r.request
        if r.provider == "firms" and r.product.endswith("_SP") and q.get("bbox") == UK_BBOX:
            df, _ = normalize_firms(read_firms_csv(archive.read(r)), r.product)
            frames.append(df)
    sp = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["source", "satellite", "latitude", "longitude",
                                                                      "acq_datetime_utc", "frp"])
    sp = filter_qualifying(sp)
    sp = sp[sp["acq_datetime_utc"] < pd.Timestamp("2026-07-01", tz="UTC")]
    nrt = pd.read_parquet(data_dir() / "live" / "live_detections.parquet")
    nrt = nrt[nrt["acq_datetime_utc"] >= pd.Timestamp("2026-07-01", tz="UTC")]
    det = pd.concat([sp[["latitude", "longitude", "acq_datetime_utc", "frp", "source"]],
                     nrt[["latitude", "longitude", "acq_datetime_utc", "frp", "source"]]], ignore_index=True)
    det = det[(det["acq_datetime_utc"] >= SEASON[0]) & (det["acq_datetime_utc"] < SEASON[1] + pd.Timedelta(days=1))]
    det["district"] = assign_regions(det["latitude"], det["longitude"], districts).to_numpy()
    det = det[det["district"].notna()]

    sat = det.groupby("district").agg(detections=("latitude", "size"), frp_sum=("frp", "sum"),
                                      detection_days=("acq_datetime_utc", lambda s: s.dt.date.nunique()))
    rng = np.random.default_rng(SEED)
    results, tables = [], {}
    for label, d in (("all divisions", div), ("excluding multi-district divisions", div[~div["multi"]])):
        ground = d.groupby("district").agg(incidents=("Total Incidents", "sum"),
                                           area_ha=("Total Affected Area (Ha)", "sum"))
        t = ground.join(sat, how="outer").fillna(0).reindex(districts["region"]).fillna(0)
        tables[label] = t
        for gcol in ("incidents", "area_ha"):
            for scol in ("detections", "detection_days", "frp_sum"):
                rho, p = spearman_perm(t[gcol].to_numpy(), t[scol].to_numpy(), rng)
                results.append({"set": label, "ground": gcol, "satellite": scol, "spearman_rho": rho,
                                "perm_p_two_sided": p, "n_districts": len(t)})

    now = datetime.now(UTC)
    t_all = tables["all divisions"].sort_values("incidents", ascending=False)
    lines = [f"# Uttarakhand: ground-reported incidents vs VIIRS detections — {now:%Y-%m-%d %H:%M} UTC", "",
             "Secondary validation of *detections* (not day-level predictions). Ground data: Uttarakhand Forest "
             f"Department division-wise bulletin snapshot `{snap.path}` (retrieved {snap.retrieved_at_utc[:16]} UTC), "
             "2026 season 15 Feb – 15 Oct. Satellite: qualifying VIIRS S-NPP + NOAA-20 detections (SP to 30 Jun, NRT "
             "after), same period, assigned to geoBoundaries ADM2 districts.", "",
             f"- Ground total: {int(div['Total Incidents'].sum())} incidents, "
             f"{div['Total Affected Area (Ha)'].sum():.1f} ha, across {len(div)} divisions → 13 districts",
             f"- Satellite total in Uttarakhand: {len(det):,} detections", "",
             "## Rank correlations (Spearman, 20,000-permutation p-values; n = 13 districts)", "",
             pd.DataFrame(results).round(3).to_markdown(index=False), "",
             "## District table (all divisions)", "", t_all.round(1).to_markdown(), "",
             "Caveats: one season, 13 units; the division→district mapping is approximate (see config); ground "
             "incidents count forest-department-recorded fires on forest land only, while satellite detections "
             "include agricultural and non-forest fires."]
    out = REPO_ROOT / "reports" / "experiment_summaries" / f"uttarakhand_validation_{now:%Y%m%dT%H%M}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"Wrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
