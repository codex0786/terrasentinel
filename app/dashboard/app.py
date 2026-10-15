"""TerraSentinel research dashboard (prototype).

Shows, for one UTC day D: satellite fire detections observed on D, and next-day persistence
predictions made at D 00:00 UTC for cells that had a detection on D-1. Observations and
predictions are drawn differently and labelled separately.

    streamlit run app/dashboard/app.py
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pydeck as pdk
import streamlit as st
import yaml

from terrasentinel.config import REPO_ROOT, data_dir

EXPERIMENT = "fire_persistence_v0"
PROC = data_dir() / "processed" / EXPERIMENT
MODELS = {
    "B1": "B1 · satellite history (recommended)",
    "M2": "M2 · B1 + weather (no robust gain on test)",
    "B0": "B0 · seasonal baseline",
}
SET_NOTE = {
    "train": ("In-sample", "This date is in the training period (2020–2022). The models saw these outcomes; "
              "performance here is optimistic.", "warning"),
    "val": ("Validation", "2023 validation period: out-of-sample, used during development.", "info"),
    "test": ("Locked test", "2024 locked test period: out-of-sample, scored once under the protocol.", "success"),
    "geo_train_excluded": ("Held-out state", "Held-out state during the training years: never used for training.",
                           "info"),
    "geo_val": ("Held-out state", "Held-out state, 2023.", "info"),
    "geo_test": ("Held-out state", "Held-out state, 2024 (locked test).", "success"),
    "embargo": ("Embargo", "Gap between periods; excluded from training and evaluation.", "info"),
}

st.set_page_config(page_title="TerraSentinel", page_icon="🛰️", layout="wide")


@st.cache_data(show_spinner="Loading predictions…")
def load_scores() -> pd.DataFrame:
    s = pd.read_parquet(PROC / "scores.parquet")
    s["day"] = s["date"].dt.date
    return s


@st.cache_data
def load_meta() -> tuple[dict, dict, list[date]]:
    meta = json.loads((PROC / "scores_meta.json").read_text())
    manifest = json.loads((PROC / "manifest.json").read_text())
    unobserved = [date.fromisoformat(d) for d in manifest.get("unobserved_label_days_excluded", [])]
    return meta, manifest, unobserved


@st.cache_data(show_spinner="Loading detections…", max_entries=16)
def load_detections(day: date) -> pd.DataFrame:
    start = pd.Timestamp(day, tz="UTC")
    t = pq.read_table(PROC / "detections.parquet",
                      columns=["latitude", "longitude", "acq_datetime_utc", "frp", "satellite", "source",
                               "confidence_class", "daynight", "region"],
                      filters=[("acq_datetime_utc", ">=", start),
                               ("acq_datetime_utc", "<", start + pd.Timedelta(days=1))])
    return t.to_pandas()


@st.cache_data
def locked_results() -> pd.DataFrame:
    return pd.DataFrame({
        "Test set": ["Training states (2024)", "Held-out states (2024)"],
        "Prevalence": [0.360, 0.423],
        "B0 PR-AUC": [0.651, 0.686], "B1 PR-AUC": [0.683, 0.724], "M2 PR-AUC": [0.685, 0.724],
        "M2 − B1 [95% CI]": ["+0.002 [−0.000, +0.004]", "+0.001 [−0.003, +0.005]"],
        "B1 − B0 [95% CI]": ["+0.031 [+0.020, +0.042]", "+0.038 [+0.016, +0.056]"],
    })


def color_for(p: np.ndarray) -> list[list[int]]:
    """Sequential blue scale for probability (distinct from the warm colour used for observations)."""
    p = np.clip(p, 0, 1)
    lo, hi = np.array([158, 202, 225]), np.array([8, 48, 107])
    rgb = (lo + (hi - lo) * p[:, None]).astype(int)
    return [[*c, 220] for c in rgb.tolist()]


scores = load_scores()
meta, manifest, unobserved = load_meta()
first, last = scores["day"].min(), scores["day"].max()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("TerraSentinel")
    st.caption("Research prototype · India · VIIRS active fire")
    day = st.date_input("UTC day D", value=date(2024, 4, 15), min_value=first, max_value=last)
    model = st.radio("Prediction model", list(MODELS), format_func=MODELS.get)
    show_obs = st.checkbox("Observed detections on D", value=True)
    show_pred = st.checkbox("Predictions for D (made at D 00:00 UTC)", value=True)
    reveal = st.checkbox("Reveal outcome (was fire detected on D?)", value=False,
                         help="Shows whether each predicted cell actually had a detection on D.")
    only_flagged = st.checkbox("Only top-10% flagged cells", value=False)
    st.divider()
    st.caption(f"Model code `{meta['code_commit']}` · trained {meta['trained_on']}")
    st.caption("Not an emergency warning service. For official information see NDMA, IMD and "
               "state forest departments.")

st.title("Fire persistence — India")
st.caption(f"**{day:%A %d %B %Y}** (UTC). Predictions estimate whether a fire detected on "
           f"{day - timedelta(days=1):%d %b} is detected again on {day:%d %b}. They are not ignition forecasts.")

if day in unobserved:
    st.error("**No predictions or labels for this day.** At least one satellite (S-NPP or NOAA-20) recorded "
             "no observations over India, so 'no detection' would not mean 'no fire'. "
             "This day is excluded from the study.")

today = scores[scores["day"] == day].copy()
det = load_detections(day) if show_obs else pd.DataFrame()

if len(today):
    sets = today["set"].value_counts()
    title, note, kind = SET_NOTE[sets.index[0]]
    getattr(st, kind)(f"**{title}.** {note}" + ("" if len(sets) == 1 else
                       " Some cells on this day are in held-out states (never used for training)."))

pcol = f"p_{model}"
if len(today):
    k = int(np.ceil(0.10 * len(today)))
    today = today.sort_values([pcol, "cell_id"], ascending=[False, True])
    today["flagged"] = False
    today.iloc[:k, today.columns.get_loc("flagged")] = True

# ---------------------------------------------------------------- KPIs
c1, c2, c3, c4 = st.columns(4)
c1.metric("Detections observed on D", f"{len(load_detections(day)):,}",
          help="Qualifying (nominal/high confidence) S-NPP + NOAA-20 detections inside India.")
c2.metric("Cells predicted", f"{len(today):,}", help="Cells with a detection on D−1 (the eligible population).")
c3.metric("Flagged (top 10%)", f"{int(today['flagged'].sum()) if len(today) else 0:,}")
if reveal and len(today):
    fl = today[today["flagged"]]
    c4.metric("Flagged that persisted", f"{fl['label'].mean():.0%}",
              delta=f"{fl['label'].mean() - today['label'].mean():+.0%} vs all eligible",
              help="Share of flagged cells with a detection on D. Revealed only on request.")
else:
    c4.metric("Flagged that persisted", "hidden", help="Tick 'Reveal outcome' to compare predictions with D.")

# ---------------------------------------------------------------- map
layers = []
if show_obs and len(det):
    d = det.assign(kind="Observation", t=det["acq_datetime_utc"].dt.strftime("%H:%M UTC"),
                   frp_s=det["frp"].round(1).astype(str))
    layers.append(pdk.Layer("ScatterplotLayer", d[["longitude", "latitude", "kind", "t", "satellite", "frp_s",
                                                   "confidence_class", "region"]],
                            get_position=["longitude", "latitude"], get_fill_color=[230, 85, 13, 200],
                            get_radius=1200, radius_min_pixels=1, radius_max_pixels=4, opacity=0.7, pickable=True))

if show_pred and len(today):
    view = today[today["flagged"]] if only_flagged else today
    view = view.assign(
        fill=color_for(view[pcol].to_numpy()),
        line=[[220, 20, 60, 255] if f else [255, 255, 255, 160] for f in view["flagged"]],
        prob=(view[pcol] * 100).round(0).astype(int).astype(str) + "%",
        outcome=np.where(view["label"] == 1, "detected on D", "not detected on D") if reveal else "hidden",
        kind="Prediction",
    )
    # Circles with a minimum on-screen size: a 0.1-degree cell (~11 km) is ~1 px at national zoom.
    layers.append(pdk.Layer("ScatterplotLayer", view[["lon", "lat", "fill", "line", "prob", "outcome", "kind",
                                                      "cell_id", "cell_region", "fire_count_1d"]],
                            get_position=["lon", "lat"], get_fill_color="fill", get_line_color="line",
                            get_radius=5500, radius_min_pixels=3, radius_max_pixels=30,
                            stroked=True, line_width_min_pixels=1, pickable=True))
tooltip = {"html": "<b>{kind}</b><br/>{cell_id}{t} · {cell_region}{region}<br/>"
                   "P(persist) {prob} {satellite} FRP {frp_s}<br/>detections on D−1: {fire_count_1d}"
                   "<br/>{outcome}{confidence_class}",
           "style": {"fontSize": "12px"}}
st.pydeck_chart(pdk.Deck(layers=layers, map_provider="carto", map_style="light", tooltip=tooltip,
                         initial_view_state=pdk.ViewState(latitude=22.5, longitude=80.5, zoom=4.0)),
                height=600)
st.caption("🟠 Observed detections on D (satellite pixels, not ground-verified)   ·   "
           "🔵 Predicted probability that a D−1 fire is detected again on D (darker = higher; "
           "red outline = top-10% flagged)")

# ---------------------------------------------------------------- evidence
left, right = st.columns([3, 2])
with left:
    st.subheader("Highest-probability cells")
    if len(today):
        top = today.head(15)[["cell_id", "cell_region", pcol, "fire_count_1d", "frp_sum_1d", "label"]].rename(columns={
            "cell_id": "Cell", "cell_region": "State", pcol: "P(persist)", "fire_count_1d": "Detections D−1",
            "frp_sum_1d": "FRP D−1 (MW)", "label": "Detected on D"})
        if not reveal:
            top = top.drop(columns=["Detected on D"])
        st.dataframe(top.style.format({"P(persist)": "{:.0%}", "FRP D−1 (MW)": "{:.1f}"}), hide_index=True,
                     use_container_width=True)
    else:
        st.write("No eligible cells on this day.")
with right:
    st.subheader("By state")
    if len(today):
        by = today.groupby("cell_region").agg(cells=("cell_id", "size"), flagged=("flagged", "sum"),
                                             mean_p=(pcol, "mean")).sort_values("cells", ascending=False).head(10)
        st.dataframe(by.rename(columns={"cells": "Eligible", "flagged": "Flagged", "mean_p": "Mean P"})
                     .rename_axis("State").style.format({"Mean P": "{:.0%}"}), use_container_width=True)

# ---------------------------------------------------------------- methods & provenance
tab1, tab2, tab3 = st.tabs(["Locked test results", "Data provenance", "Limitations"])
with tab1:
    st.markdown("Pre-registered evaluation (protocol commit `e0c9385`), 2024 test year, scored once. "
                "PR-AUC; 95% block-bootstrap CIs (state × ISO week).")
    st.dataframe(locked_results(), hide_index=True, use_container_width=True)
    st.markdown("**Conclusion:** adding NASA POWER weather (M2) gave **no robust improvement** over satellite "
                "history (B1). Satellite history robustly beat the seasonal baseline (B0), including in "
                "held-out states (Odisha, Haryāna, Mizoram).")
with tab2:
    exp = yaml.safe_load((REPO_ROOT / "configs" / "experiments" / f"{EXPERIMENT}.yaml").read_text())
    st.markdown(
        f"- **Detections:** NASA FIRMS VIIRS science-quality (`{'`, `'.join(exp['dataset']['sources'])}`), "
        "nominal/high confidence, clipped to India (geoBoundaries ADM1).\n"
        "- **Weather (M2 only):** NASA POWER / MERRA-2 daily, UTC, nearest ≈0.5° × 0.625° grid point.\n"
        f"- **Grid:** 0.1° cells. **Horizon:** {meta['horizon']}.\n"
        f"- **Models trained on:** {meta['trained_on']}. Scored {meta['scored_at_utc']} at commit "
        f"`{meta['code_commit']}`.\n"
        f"- **Days excluded for sensor outages:** {len(unobserved)} "
        f"({', '.join(d.isoformat() for d in unobserved[:4])}, …)."
    )
    if show_obs and len(det):
        st.caption(f"Detections on D by satellite: {det['satellite'].value_counts().to_dict()}; "
                   f"day/night: {det['daynight'].value_counts().to_dict()}")
with tab3:
    st.markdown((REPO_ROOT / "docs" / "limitations.md").read_text().split("\n", 2)[2])
