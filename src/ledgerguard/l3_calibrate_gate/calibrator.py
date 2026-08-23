"""L3 calibrator (phases.md Phase 5 task 2): logistic regression over the full feature vector
(features.py), fit on validation labels only. `predict_proba` is what "calibrated_confidence"
means everywhere else in this project -- never the raw rule/model confidence directly.

Fit on validation. Report on holdout. Never fit on holdout (phases.md's explicit instruction) --
callers are responsible for only ever passing validation-split decisions to `fit()`.
"""
from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression

from ledgerguard.l3_calibrate_gate.features import FEATURE_NAMES


def _to_matrix(feature_dicts: list[dict[str, float]]) -> np.ndarray:
    return np.array([[fd[name] for name in FEATURE_NAMES] for fd in feature_dicts])


class Calibrator:
    def __init__(self) -> None:
        self._model = LogisticRegression(max_iter=1000)
        self._fitted = False

    def fit(self, feature_dicts: list[dict[str, float]], labels: list[bool]) -> None:
        x = _to_matrix(feature_dicts)
        y = np.array(labels, dtype=int)
        if len(set(y.tolist())) < 2:
            raise ValueError("Calibrator.fit needs both correct and incorrect examples in the training data")
        self._model.fit(x, y)
        self._fitted = True

    def predict_proba(self, feature_dicts: list[dict[str, float]]) -> list[float]:
        if not self._fitted:
            raise RuntimeError("Calibrator.predict_proba called before fit()")
        x = _to_matrix(feature_dicts)
        # probability of the positive class (label = correct)
        return self._model.predict_proba(x)[:, 1].tolist()
