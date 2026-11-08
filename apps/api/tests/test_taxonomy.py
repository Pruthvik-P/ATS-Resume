from __future__ import annotations

from app.services.scoring.embedding import similarity
from app.taxonomy.skills import canonical_for, find_skills


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
