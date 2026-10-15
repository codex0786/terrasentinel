import json

import numpy as np
import pandas as pd
import pytest

from terrasentinel.models.baselines import LogisticModel
from terrasentinel.models.frozen import FrozenLogistic, export_logistic


def data(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"a": rng.poisson(3, n), "b": rng.gamma(2, 5, n), "t": rng.normal(30, 5, n)})
    df.loc[rng.random(n) < 0.05, "b"] = np.nan
    df["label"] = (rng.random(n) < 1 / (1 + np.exp(-(0.3 * df["a"] - 2)))).astype(int)
    return df


@pytest.mark.parametrize("log_features", [None, ["a", "b"]])
def test_frozen_equals_sklearn(log_features):
    df = data()
    m = LogisticModel(["a", "b", "t"] if log_features else ["a", "b"], name="X", log_features=log_features).fit(df)
    frozen = FrozenLogistic(json.loads(json.dumps(export_logistic(m))))
    test = data(500, seed=1)
    np.testing.assert_allclose(frozen.predict(test), m.predict(test), rtol=1e-10, atol=1e-12)


def test_tampered_file_rejected():
    m = LogisticModel(["a", "b"]).fit(data())
    spec = export_logistic(m)
    spec["coef"][0] += 1.0
    with pytest.raises(ValueError, match="sha256"):
        FrozenLogistic(spec)
