from __future__ import annotations

import json

from app.core.config import settings
from app.services.scoring.embedding import similarity
from app.taxonomy.skills import (
    canonical_for,
    find_skills,
    load_external_taxonomy,
    reset_external_taxonomy,
    taxonomy_version,
)


def test_alias_normalisation():
    assert canonical_for("k8s") == "Kubernetes"
    assert canonical_for("postgres") == "PostgreSQL"
    assert canonical_for("js") == "JavaScript"


def test_find_skills_maps_aliases():
    found = {match.canonical for match in find_skills("Built with K8s, Postgres and JS")}
    assert {"Kubernetes", "PostgreSQL", "JavaScript"} <= found


def test_ambiguous_go_alias_needs_context():
    assert not any(match.canonical == "Go" for match in find_skills("We go to market quickly"))
    assert any(match.canonical == "Go" for match in find_skills("Languages: Go, Python"))


def test_java_does_not_match_javascript():
    found = {match.canonical for match in find_skills("JavaScript and TypeScript")}
    assert "Java" not in found
    assert "JavaScript" in found


def test_embedding_similarity_is_deterministic_and_ranked():
    close = similarity("built CI pipelines with Jenkins", "maintain CI/CD pipelines")
    far = similarity("built CI pipelines with Jenkins", "planted tomatoes in the garden")
    assert close > far
    assert similarity("same text", "same text") > 0.99


def test_semantic_fallback_matches_paraphrase():
    relevant = similarity("deployed container orchestration", "Kubernetes experience")
    unrelated = similarity("deployed container orchestration", "graphic design portfolio")
    assert relevant > unrelated


def test_external_json_taxonomy_is_loaded(tmp_path):
    path = tmp_path / "skills.json"
    path.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "COBOL",
                        "aliases": ["cobol85", "cobol 85"],
                        "category": "language",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    reset_external_taxonomy()
    try:
        before = taxonomy_version()
        assert load_external_taxonomy(path) == 1
        assert canonical_for("cobol85") == "COBOL"
        assert any(
            match.canonical == "COBOL" for match in find_skills("Migrated COBOL85 systems")
        )
        assert taxonomy_version() != before
    finally:
        reset_external_taxonomy()


def test_external_csv_taxonomy_accepts_alt_labels(tmp_path):
    path = tmp_path / "onet.csv"
    path.write_text(
        "preferredLabel,altLabels,skillType\n"
        "Mainframe Operations,IBM z/OS|JCL,skill\n",
        encoding="utf-8",
    )
    reset_external_taxonomy()
    try:
        assert load_external_taxonomy(path) == 1
        assert canonical_for("jcl") == "Mainframe Operations"
        assert canonical_for("ibm z/os") == "Mainframe Operations"
    finally:
        reset_external_taxonomy()


def test_configured_taxonomy_loads_lazily(tmp_path, monkeypatch):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps([{"canonical": "Quantum Computing", "aliases": ["qiskit"]}]),
        encoding="utf-8",
    )
    reset_external_taxonomy()
    monkeypatch.setattr(settings, "taxonomy_paths", str(path))
    try:
        assert canonical_for("qiskit") == "Quantum Computing"
    finally:
        reset_external_taxonomy()
