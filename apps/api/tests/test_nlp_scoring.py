from __future__ import annotations

from app.core.config import settings
from app.schemas.resume import Resume
from app.services.ingest.pipeline import ingest_bytes
from app.services.jd_analyser import analyse_jd
from app.services.scoring.bm25 import BM25, bm25_similarity
from app.services.scoring.embedding import (
    active_embedding_model,
    embed,
    embedding_bands,
    reset_embedder,
)
from app.services.scoring.engine import build_score_report
from app.services.scoring.fairness import anonymise_resume
from app.services.scoring.keyword import score_keywords
from app.services.scoring.rerank import get_reranker, reset_reranker
from app.services.scoring.semantic import score_semantics
from app.services.text import fuzzy_contains, lemmatize
from tests.conftest import SAMPLE_JD, SAMPLE_TEX


def test_bm25_ranks_relevant_documents_higher():
    index = BM25(
        [
            "Built FastAPI services backed by PostgreSQL and Redis.",
            "Planted tomatoes and maintained the garden.",
        ]
    )
    scores = index.normalized_scores("FastAPI PostgreSQL backend")
    assert scores[0] > scores[1]
    assert scores[0] == 1.0


def test_bm25_pair_similarity_is_bounded():
    relevant = bm25_similarity("Kubernetes deployment", "Deployed services with Kubernetes")
    unrelated = bm25_similarity("Kubernetes deployment", "Planted tomatoes")
    assert 0.0 <= unrelated < relevant <= 1.0


def test_fuzzy_matching_catches_typos_without_false_positives():
    assert fuzzy_contains("Worked with Kubernetees clusters", "Kubernetes", 85)
    assert not fuzzy_contains("Planted tomatoes and basil", "Kubernetes", 88)


def test_lemmatize_uses_deterministic_fallback(monkeypatch):
    monkeypatch.setattr(settings, "spacy_enabled", False)
    terms = lemmatize("Built production services")
    assert terms
    assert "servic" in terms


def test_embedding_provider_falls_back_without_optional_model(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "sentence-transformers")
    monkeypatch.setattr(settings, "embedding_model", "model-that-does-not-exist")
    reset_embedder()
    try:
        model = active_embedding_model()
        assert "hashed-ngram-v1" in model
        vector = embed("deterministic fallback")
        assert len(vector) == settings.embedding_dim
    finally:
        reset_embedder()


def test_embedding_bands_default_to_hashed():
    reset_embedder()
    low, high, model = embedding_bands()
    assert model == "hashed-ngram-v1"
    assert low < high


def test_fuzzy_skill_match_is_explainable():
    resume = Resume.model_validate(
        {
            "basics": {"name": "Jane Doe", "email": "jane@example.com"},
            "work": [
                {
                    "name": "Acme",
                    "position": "Engineer",
                    "highlights": ["Worked with Kubernetees clusters in production."],
                }
            ],
            "skills": [{"name": "Cloud", "keywords": ["Docker"]}],
        }
    )
    analysis, _ = analyse_jd("Requirements\n- Kubernetes required\n- Python required")
    result, details = score_keywords(resume, analysis)

    assert "Kubernetes" in result.matched
    evidence = next(item for item in details["evidence"] if item["skill"] == "Kubernetes")
    assert evidence["location"] == "fuzzy_fallback"
    assert evidence["credit"] < 1.0


class _FakeReranker:
    name = "fake-cross-encoder"
    model_name = "fake-model"

    def score(self, query: str, candidates: list[str]) -> list[float]:
        return [0.95 if "kubernetes" in candidate.lower() else 0.05 for candidate in candidates]


def test_cross_encoder_reranker_can_promote_evidence(monkeypatch):
    monkeypatch.setattr(settings, "reranker_weight", 1.0)
    resume = Resume.model_validate(
        {
            "basics": {"name": "Jane Doe", "email": "jane@example.com"},
            "work": [
                {
                    "name": "Acme",
                    "position": "Engineer",
                    "highlights": [
                        "Planted tomatoes and maintained the garden.",
                        "Operated Kubernetes clusters in production.",
                    ],
                }
            ],
        }
    )
    analysis, _ = analyse_jd("Responsibilities\n- Operate Kubernetes clusters")
    result, details = score_semantics(resume, analysis, reranker=_FakeReranker())

    assert details["reranker"] == "fake-cross-encoder"
    assert result.requirement_matches
    top = result.requirement_matches[0]
    assert "Kubernetes" in str(top["evidence"])


def test_reranker_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "reranker_enabled", False)
    reset_reranker()
    assert get_reranker() is None


def test_fairness_view_removes_contact_and_protected_terms():
    resume = Resume.model_validate(
        {
            "basics": {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "+1 415 555 0123",
                "url": "https://example.com",
                "summary": (
                    "Age 35. He/him. Nationality: Indian. Married. "
                    "Lives at 123 Main Street."
                ),
                "location": {"city": "Austin", "region": "TX"},
                "profiles": [{"network": "LinkedIn", "url": "https://linkedin.com/in/x"}],
            },
            "work": [
                {
                    "name": "Acme",
                    "position": "Engineer",
                    "highlights": ["She led a team of engineers."],
                }
            ],
        }
    )
    view = anonymise_resume(resume)
    assert view.resume.basics.name is None
    assert view.resume.basics.email is None
    assert view.resume.basics.phone is None
    assert view.resume.basics.location is None
    assert view.resume.basics.profiles == []
    assert "[redacted]" in (view.resume.basics.summary or "")
    assert "she" not in view.resume.work[0].highlights[0].lower()
    assert view.redactions["gender_pronouns"] >= 1
    assert view.redactions.get("age", 0) >= 1
    assert view.audit["total_redactions"] > 0
    assert view.audit["contact_removed"] is True


def test_score_report_keeps_parseability_original_while_scoring_anonymised(monkeypatch):
    monkeypatch.setattr(settings, "fairness_redaction_enabled", True)
    document = ingest_bytes("jane.tex", None, SAMPLE_TEX.encode("utf-8")).document
    analysis, _ = analyse_jd(SAMPLE_JD)
    report = build_score_report(
        resume_id="resume-1", jd_id="jd-1", document=document, analysis=analysis
    )
    assert report.fairness["enabled"] is True
    assert report.fairness["contact_removed"] is True
    # Parseability still sees the real name/email and keeps its recall.
    assert report.breakdown.parseability.model_extra["field_recall"] > 80


def test_fairness_can_be_disabled(monkeypatch):
    monkeypatch.setattr(settings, "fairness_redaction_enabled", False)
    document = ingest_bytes("jane.tex", None, SAMPLE_TEX.encode("utf-8")).document
    analysis, _ = analyse_jd(SAMPLE_JD)
    report = build_score_report(
        resume_id="resume-1", jd_id="jd-1", document=document, analysis=analysis
    )
    assert report.fairness == {}


