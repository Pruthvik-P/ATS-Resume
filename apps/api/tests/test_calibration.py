from __future__ import annotations

import json

from app.core.config import settings
from app.services.ingest.pipeline import ingest_bytes
from app.services.jd_analyser import analyse_jd
from app.services.scoring.calibration import (
    FEATURE_NAMES,
    fit_calibration,
    load_calibration,
    spearman,
)
from app.services.scoring.engine import build_score_report
from tests.conftest import SAMPLE_JD, SAMPLE_TEX


def _rows() -> list[tuple[list[float], int]]:
    return [
        ([90, 92, 85, 90, 85, 75, 80], 1),
        ([85, 88, 80, 85, 80, 70, 78], 1),
        ([20, 25, 30, 42, 25, 30, 55], 0),
        ([30, 22, 28, 38, 30, 32, 50], 0),
        ([70, 68, 65, 75, 60, 60, 70], 1),
        ([35, 30, 32, 45, 35, 35, 58], 0),
    ]


def test_logistic_calibration_learns_direction():
    model = fit_calibration(_rows(), epochs=1500, learning_rate=0.4)
    assert model.version == "logistic-v1"
    high = model.predict_proba([90, 92, 85, 90, 85, 75, 80])
    low = model.predict_proba([20, 25, 30, 42, 25, 30, 55])
    assert high > low
    assert high > 0.55
    assert low < 0.45


def test_spearman_ranks_correctly():
    assert spearman([0.1, 0.4, 0.35, 0.8], [0, 1, 0, 1]) > 0.7
    assert spearman([1, 2, 3], [3, 2, 1]) < -0.9


def test_calibration_model_round_trips(tmp_path):
    model = fit_calibration(_rows(), epochs=300)
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(model.to_dict()), encoding="utf-8")
    loaded = load_calibration(path)
    assert loaded.version == model.version
    assert loaded.weights == model.weights
    assert loaded.intercept == model.intercept


def test_score_report_records_calibration(monkeypatch, tmp_path):
    model = fit_calibration(_rows(), epochs=800, learning_rate=0.4)
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps(model.to_dict()), encoding="utf-8")
    monkeypatch.setattr(settings, "calibration_enabled", True)
    monkeypatch.setattr(settings, "calibration_path", str(path))
    monkeypatch.setattr(settings, "calibration_blend_weight", 0.0)

    document = ingest_bytes("jane.tex", None, SAMPLE_TEX.encode("utf-8")).document
    analysis, _ = analyse_jd(SAMPLE_JD)
    report = build_score_report(
        resume_id="resume-1", jd_id="jd-1", document=document, analysis=analysis
    )

    assert report.calibration["version"] == model.version
    assert 0.0 <= report.calibration["probability"] <= 1.0
    assert set(report.calibration["features"]) == set(FEATURE_NAMES)
    assert report.model_versions["calibration"] == model.version


def test_calibration_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "calibration_enabled", False)
    document = ingest_bytes("jane.tex", None, SAMPLE_TEX.encode("utf-8")).document
    analysis, _ = analyse_jd(SAMPLE_JD)
    report = build_score_report(
        resume_id="resume-1", jd_id="jd-1", document=document, analysis=analysis
    )
    assert report.calibration == {}
