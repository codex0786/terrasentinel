"""Frozen (exported) logistic models: score with numpy from a small JSON file, no training data needed.

The JSON holds exactly what the fitted sklearn pipeline uses: per-feature imputation medians, whether
log1p is applied, scaler mean/scale, coefficients and intercept. `tests/unit/test_frozen_model.py` checks
that frozen predictions equal the sklearn pipeline's.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from terrasentinel.models.baselines import LogisticModel

SCHEMA = "terrasentinel.frozen_logistic.v1"


def export_logistic(model: LogisticModel, extra: dict | None = None) -> dict:
    ct, scaler, lr = model.model_[0], model.model_[1], model.model_[-1]
    medians: dict[str, float] = {}
    log_set = set(model.log_features)
    for name, trans, cols in ct.transformers_:
        if name == "remainder":
            continue
        imputer = trans[0] if hasattr(trans, "steps") else trans
        medians.update({c: float(v) for c, v in zip(cols, imputer.statistics_, strict=True)})
    order = model.log_features + model.linear_features          # ColumnTransformer output order
    out = {
        "schema": SCHEMA,
        "name": model.name,
        "features": order,
        "log1p": [f in log_set for f in order],
        "impute_median": [medians[f] for f in order],
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": lr.coef_[0].tolist(),
        "intercept": float(lr.intercept_[0]),
    }
    out.update(extra or {})
    body = json.dumps({k: v for k, v in out.items() if k != "sha256"}, sort_keys=True).encode()
    out["sha256"] = hashlib.sha256(body).hexdigest()
    return out


class FrozenLogistic:
    def __init__(self, spec: dict):
        if spec.get("schema") != SCHEMA:
            raise ValueError(f"unsupported model schema {spec.get('schema')!r}")
        body = json.dumps({k: v for k, v in spec.items() if k != "sha256"}, sort_keys=True).encode()
        if hashlib.sha256(body).hexdigest() != spec.get("sha256"):
            raise ValueError("frozen model file does not match its sha256 (edited or corrupted)")
        self.spec = spec
        self.features = spec["features"]
        self.name = spec["name"]

    @classmethod
    def load(cls, path: Path) -> FrozenLogistic:
        return cls(json.loads(Path(path).read_text()))

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        s = self.spec
        x = rows[self.features].to_numpy(float)
        x = np.where(np.isnan(x), np.asarray(s["impute_median"]), x)
        logm = np.asarray(s["log1p"])
        x[:, logm] = np.log1p(x[:, logm])
        z = (x - np.asarray(s["scaler_mean"])) / np.asarray(s["scaler_scale"])
        return 1.0 / (1.0 + np.exp(-(z @ np.asarray(s["coef"]) + s["intercept"])))
