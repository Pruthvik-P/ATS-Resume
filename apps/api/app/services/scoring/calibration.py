"""Calibration helpers.

The deterministic score is a proxy. This module fits a small logistic-regression
model on labelled `(features, shortlisted)` rows, reports Spearman rank
correlation, and can load a frozen JSON model for reproducible scoring.

The implementation is pure Python so calibration works without scikit-learn.
Features are the seven component scores divided by 100.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

FEATURE_NAMES: tuple[str, ...] = (
    "keyword_match",
    "semantic_relevance",
    "experience_fit",
    "parseability",
    "impact",
    "education",
    "readability",
)


@dataclass
class CalibrationModel:
    weights: list[float] = field(
        default_factory=lambda: [0.0 for _ in FEATURE_NAMES]
    )
    intercept: float = 0.0
    version: str = "identity-v1"
    feature_names: tuple[str, ...] = FEATURE_NAMES

    def predict_proba(self, features: Sequence[float]) -> float:
        if len(features) != len(self.weights):
            return 0.5
        logit = self.intercept + sum(
            weight * (float(value) / 100.0)
            for weight, value in zip(self.weights, features, strict=False)
        )
        return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, logit))))

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "feature_names": list(self.feature_names),
            "weights": self.weights,
            "intercept": self.intercept,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> CalibrationModel:
        weights = [float(value) for value in payload.get("weights", [])]  # type: ignore[union-attr]
        if len(weights) != len(FEATURE_NAMES):
            weights = [0.0 for _ in FEATURE_NAMES]
        return cls(
            weights=weights,
            intercept=float(payload.get("intercept", 0.0)),  # type: ignore[arg-type]
            version=str(payload.get("version", "external-v1")),
        )


def identity_model() -> CalibrationModel:
    return CalibrationModel(version="identity-v1")


def fit_calibration(
    rows: Sequence[tuple[Sequence[float], int]],
    *,
    epochs: int = 1200,
    learning_rate: float = 0.25,
    l2: float = 0.01,
) -> CalibrationModel:
    """Fit logistic regression with batch gradient descent."""

    usable = [
        ([float(value) / 100.0 for value in features], int(label))
        for features, label in rows
        if len(features) == len(FEATURE_NAMES)
    ]
    if not usable:
        return identity_model()

    weights = [0.0 for _ in FEATURE_NAMES]
    intercept = 0.0
    count = len(usable)
    for _ in range(max(1, epochs)):
        gradient = [0.0 for _ in FEATURE_NAMES]
        intercept_gradient = 0.0
        for features, label in usable:
            logit = intercept + sum(
                weight * value
                for weight, value in zip(weights, features, strict=False)
            )
            prediction = 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, logit))))
            error = prediction - label
            for index, value in enumerate(features):
                gradient[index] += error * value
            intercept_gradient += error
        for index in range(len(weights)):
            weights[index] -= learning_rate * (
                gradient[index] / count + l2 * weights[index]
            )
        intercept -= learning_rate * intercept_gradient / count

    return CalibrationModel(
        weights=[round(weight, 6) for weight in weights],
        intercept=round(intercept, 6),
        version="logistic-v1",
    )


def _rank(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0 for _ in values]
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        average = (index + end) / 2 + 1
        for position in range(index, end + 1):
            ranks[order[position]] = average
        index = end + 1
    return ranks


def spearman(predicted: Sequence[float], actual: Sequence[float]) -> float:
    if len(predicted) != len(actual) or len(predicted) < 2:
        return 0.0
    left, right = _rank(predicted), _rank(actual)
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    numerator = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(left, right, strict=False)
    )
    denominator = math.sqrt(
        sum((a - mean_left) ** 2 for a in left)
        * sum((b - mean_right) ** 2 for b in right)
    )
    return round(numerator / denominator, 4) if denominator else 0.0


def load_calibration(path: str | Path) -> CalibrationModel:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return CalibrationModel.from_dict(payload)


__all__ = [
    "FEATURE_NAMES",
    "CalibrationModel",
    "fit_calibration",
    "identity_model",
    "load_calibration",
    "spearman",
]
