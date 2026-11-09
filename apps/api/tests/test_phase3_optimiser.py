from __future__ import annotations

from app.schemas.jobs import ChangeProposal, OptimiseOptions
from app.schemas.resume import Resume, ResumeDocument
from app.services.jd_analyser import analyse_jd
from app.services.optimiser import (
    _plan_deterministic,
    _rewrite_bullet,
    _tailor_summary,
    apply_proposals,
)
from app.services.scoring.engine import build_score_report
from tests.conftest import SAMPLE_JD


def _document() -> ResumeDocument:
    resume = Resume.model_validate(
        {
            "basics": {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "summary": (
                    "Backend engineer with 6 years of experience. "
                    "Built Python and FastAPI services at scale. "
                    "Planted tomatoes and maintained a garden. "
                    "Managed AWS infrastructure and on-call rotations."
                ),
            },
            "work": [
                {
                    "name": "Acme",
                    "position": "Senior Engineer",
                    "startDate": "2021",
                    "endDate": "Present",
                    "highlights": [
                        "Built FastAPI services handling 2M requests per day for paying customers.",
                        "Planted tomatoes and maintained the community garden every weekend in summer.",
                        "Led a team of five engineers and mentored two junior developers over a year.",
                        "Managed AWS infrastructure with Terraform and reduced deployment time by 40%.",
                        "Built Python data pipelines with Airflow and PostgreSQL for analytics teams.",
                        "Improved batch processing reliability through query tuning and monitoring.",
                        "Documented operational runbooks and incident response procedures for the platform team.",
                        "Coordinated quarterly planning and dependency reviews across three engineering groups.",
                        "Reviewed pull requests and maintained coding standards for several shared repositories.",
                        "Automated release notes and deployment checklists for the platform services.",
                        "Partnered with product managers on roadmap sizing and delivery tradeoffs.",
                        "Trained new hires on local development setup and production support expectations.",
                        "Maintained the internal service catalog and ownership metadata for twenty services.",
                        "Improved observability dashboards for latency, error budgets, and on-call handoffs.",
                        "Wrote migration guides for teams moving workloads onto the shared platform tooling.",
                        "Partnered with security engineers to remediate dependency and access review findings.",
                        "Designed and delivered a multi-region deployment strategy with rollback support and clear ownership.",
                        "Facilitated weekly architecture reviews and recorded decisions for future maintainers of the platform.",
                        "Built internal tooling that reduced manual release coordination and improved deployment confidence.",
                        "Collaborated with support engineers to reproduce customer issues and prioritize follow-up fixes.",
                        "Presented reliability metrics and incident learnings to engineering leadership on a quarterly basis.",
                    ],
                }
            ],
            "skills": [{"name": "Languages", "keywords": ["Python", "SQL"]}],
        }
    )
    return ResumeDocument(format="tex", canonical=resume)


def test_broader_rewrite_patterns():
    assert _rewrite_bullet("In charge of building APIs.") == ("In charge of", "Built APIs.")
    assert _rewrite_bullet("Responsible for leading a team.") == (
        "Responsible for",
        "Led a team.",
    )
    assert _rewrite_bullet("Tasked with modernizing the pipeline.") == (
        "Tasked with",
        "Modernized the pipeline.",
    )


def test_summary_tailoring_preserves_facts():
    document = _document()
    analysis, _ = analyse_jd(SAMPLE_JD)
    options = OptimiseOptions(tone="concise")
    proposed = _tailor_summary(document.canonical, analysis, options)

    assert proposed
    assert len(proposed) < len(document.canonical.basics.summary or "")
    assert "Python" in proposed
    # No sentence was invented; the selected sentences all come from the source.
    for sentence in proposed.split(". "):
        assert sentence.strip(".") in (document.canonical.basics.summary or "")


def test_plan_generates_reorder_and_condense_proposals():
    document = _document()
    analysis, _ = analyse_jd(SAMPLE_JD)
    options = OptimiseOptions(max_pages=0.5, max_iterations=1)
    report = build_score_report(
        resume_id="resume-1", jd_id="jd-1", document=document, analysis=analysis
    )
    proposals, _verifier = _plan_deterministic(document, analysis, report, options)
    kinds = {proposal.kind for proposal in proposals}

    assert "summary_tailor" in kinds
    assert "reorder_bullets" in kinds
    assert "condense_bullets" in kinds
    condense = [p for p in proposals if p.kind == "condense_bullets"]
    assert all(p.truthfulness == "needs_user_input" for p in condense)
    assert all(p.target_ref and "highlights" in p.target_ref for p in condense)


def test_apply_summary_reorder_and_condense():
    document = _document()
    analysis, _ = analyse_jd(SAMPLE_JD)
    work = document.canonical.work[0]
    original_bullets = list(work.highlights)
    proposals = [
        proposal
        for proposal in _plan_deterministic(
            document,
            analysis,
            build_score_report(
                resume_id="r", jd_id="j", document=document, analysis=analysis
            ),
            OptimiseOptions(max_pages=0.5),
        )[0]
        if proposal.kind == "condense_bullets"
    ]
    first = proposals[0]
    first.status = "accepted"
    updated = apply_proposals(document, [first], analysis)
    assert len(updated.canonical.work[0].highlights) == len(original_bullets) - 1
    assert first.original not in updated.canonical.work[0].highlights

    reorder = next(
        proposal
        for proposal in _plan_deterministic(
            document,
            analysis,
            build_score_report(
                resume_id="r", jd_id="j", document=document, analysis=analysis
            ),
            OptimiseOptions(),
        )[0]
        if proposal.kind == "reorder_bullets"
    )
    reorder.status = "accepted"
    reordered = apply_proposals(document, [reorder], analysis)
    assert sorted(reordered.canonical.work[0].highlights) == sorted(original_bullets)
    assert reordered.canonical.work[0].highlights != original_bullets


def test_reorder_and_rewrite_do_not_overwrite_each_other():
    document = ResumeDocument(
        format="tex",
        canonical=Resume.model_validate(
            {
                "basics": {"name": "Jane Doe", "email": "jane@example.com"},
                "work": [
                    {
                        "name": "Acme",
                        "position": "Engineer",
                        "highlights": [
                            "Responsible for leading a team.",
                            "Planted tomatoes in the garden.",
                        ],
                    }
                ],
            }
        ),
    )
    analysis, _ = analyse_jd(SAMPLE_JD)
    rewrite = ChangeProposal(
        id="rewrite",
        kind="rewrite_bullet",
        section="experience",
        target_ref="work[0].highlights[0]",
        original="Responsible for leading a team.",
        proposed="Led a team.",
        rationale="test",
        status="accepted",
    )
    reorder = ChangeProposal(
        id="reorder",
        kind="reorder_bullets",
        section="experience",
        target_ref="work[0].highlights",
        original="Responsible for leading a team.\nPlanted tomatoes in the garden.",
        proposed="Planted tomatoes in the garden.\nResponsible for leading a team.",
        rationale="test",
        status="accepted",
    )
    updated = apply_proposals(document, [rewrite, reorder], analysis)
    highlights = updated.canonical.work[0].highlights
    assert highlights == ["Planted tomatoes in the garden.", "Led a team."]

