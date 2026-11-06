from __future__ import annotations

import json
import re
from uuid import uuid4

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.jd import JDAnalysis
from app.schemas.jobs import (
    ChangeProposal,
    OptimiseOptions,
    OptimiseResult,
    VerifierSummary,
)
from app.schemas.resume import Resume, ResumeDocument, SkillGroup
from app.schemas.score import ScoreReport
from app.services.llm.base import get_llm_provider
from app.services.llm.prompts import PROMPT_VERSION, REWRITER_SYSTEM_PROMPT
from app.services.scoring.engine import build_score_report
from app.services.verifier import verify_rewrite, verify_skill_reorder
from app.taxonomy.skills import canonical_for, find_skills

logger = get_logger(__name__)

_WEAK_PREFIX_RE = re.compile(
    r"^(?:responsible for|duties included|worked on|helped with|helped to|"
    r"assisted with|involved in|participated in|tasked with)\s+",
    re.IGNORECASE,
)

_GERUND_TO_PAST = {
    "building": "built",
    "developing": "developed",
    "designing": "designed",
    "leading": "led",
    "managing": "managed",
    "creating": "created",
    "implementing": "implemented",
    "maintaining": "maintained",
    "deploying": "deployed",
    "automating": "automated",
    "improving": "improved",
    "reducing": "reduced",
    "supporting": "supported",
    "migrating": "migrated",
    "testing": "tested",
    "analysing": "analysed",
    "analyzing": "analyzed",
    "writing": "wrote",
    "collaborating": "collaborated",
    "coordinating": "coordinated",
    "delivering": "delivered",
    "optimizing": "optimized",
    "optimising": "optimised",
    "refactoring": "refactored",
    "scaling": "scaled",
    "shipping": "shipped",
    "launching": "launched",
}

_PARSE_FIXES: dict[str, str] = {
    "missing_glyphtounicode": (
        "Add \\input{glyphtounicode} and \\pdfgentounicode=1 to the preamble so the PDF "
        "embeds a ToUnicode map."
    ),
    "missing_fontenc": "Add \\usepackage[T1]{fontenc} to the preamble.",
    "ligature_glyphs": "Re-export the PDF with a Unicode-mapped font so ﬁ/ﬂ extract as text.",
    "private_use_glyphs": "Replace icon-font glyphs with plain text labels.",
    "docx_tables": "Convert table-based sections into stacked paragraphs.",
    "docx_text_boxes": "Move text-box content into normal body paragraphs.",
    "letter_spacing": "Remove white or hidden text entirely.",
    "spaced_letters": "Remove manual letter spacing; ATS keyword matching fails on it.",
    "fontawesome": "Replace icon fonts with text labels for contact details.",
    "icon_font": "Remove icon glyphs from headings and contact lines.",
    "tabular_layout": "Replace tabular layout with stacked sections.",
    "multi_column": "Switch to a single-column layout.",
}


def _proposal(
    *,
    kind: str,
    section: str,
    target_ref: str | None,
    original: str,
    proposed: str,
    rationale: str,
    evidence: list[str] | None = None,
    keywords: list[str] | None = None,
    truthfulness: str = "verified",
    risk: str = "low",
) -> ChangeProposal:
    return ChangeProposal(
        id=f"chg_{uuid4().hex[:12]}",
        kind=kind,  # type: ignore[arg-type]
        section=section,
        target_ref=target_ref,
        original=original,
        proposed=proposed,
        rationale=rationale,
        evidence_spans=evidence or [],
        jd_keywords_used=keywords or [],
        truthfulness=truthfulness,  # type: ignore[arg-type]
        risk=risk,  # type: ignore[arg-type]
    )


def _rank_recipe(analysis: JDAnalysis) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for requirement in analysis.nice_to_have:
        ranks[requirement.canonical] = max(ranks.get(requirement.canonical, 0), 1)
    for requirement in analysis.must_have:
        ranks[requirement.canonical] = 2
    return ranks


def _reorder_skills(resume: Resume, analysis: JDAnalysis) -> tuple[list[SkillGroup], list[SkillGroup]]:
    ranks = _rank_recipe(analysis)

    def keyword_rank(keyword: str) -> int:
        canonical = canonical_for(keyword)
        if canonical and canonical in ranks:
            return ranks[canonical]
        for match in find_skills(keyword):
            if match.canonical in ranks:
                return ranks[match.canonical]
        return 0

    indexed = list(enumerate(resume.skills))
    scored: list[tuple[int, int, int, SkillGroup]] = []
    for index, group in indexed:
        best = max((keyword_rank(keyword) for keyword in group.keywords), default=0)
        matches = sum(1 for keyword in group.keywords if keyword_rank(keyword) > 0)
        scored.append((best, matches, -index, group))
    scored.sort(reverse=True)

    reordered: list[SkillGroup] = []
    for _, _, _, group in scored:
        ordered_keywords = sorted(
            enumerate(group.keywords), key=lambda item: (-keyword_rank(item[1]), item[0])
        )
        reordered.append(
            SkillGroup(
                id=group.id,
                name=group.name,
                level=group.level,
                keywords=[keyword for _, keyword in ordered_keywords],
            )
        )
    return resume.skills, reordered


def _render_skills(groups: list[SkillGroup]) -> str:
    return " | ".join(
        f"{group.name or 'Skills'}: {', '.join(group.keywords)}" for group in groups
    )


def _rewrite_bullet(text: str) -> tuple[str, str] | None:
    match = _WEAK_PREFIX_RE.match(text)
    if not match:
        return None
    remainder = text[match.end() :].strip()
    if not remainder:
        return None
    first, _, tail = remainder.partition(" ")
    past = _GERUND_TO_PAST.get(first.lower().rstrip(","))
    if not past:
        return None
    rewritten = past.capitalize() + (f" {tail}" if tail else "")
    if not rewritten.endswith((".", "!", "?")):
        rewritten += "."
    return match.group(0).strip(), rewritten


def _iter_bullet_refs(resume: Resume) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for work_index, work in enumerate(resume.work):
        for highlight_index, highlight in enumerate(work.highlights):
            refs.append((f"work[{work_index}].highlights[{highlight_index}]", highlight))
    for project_index, project in enumerate(resume.projects):
        for highlight_index, highlight in enumerate(project.highlights):
            refs.append(
                (f"projects[{project_index}].highlights[{highlight_index}]", highlight)
            )
    return refs


def _plan_deterministic(
    document: ResumeDocument,
    analysis: JDAnalysis,
    report: ScoreReport,
    options: OptimiseOptions,
) -> tuple[list[ChangeProposal], VerifierSummary]:
    resume = document.canonical
    proposals: list[ChangeProposal] = []
    verifier = VerifierSummary()

    if options.reorder_skills and resume.skills:
        original, reordered = _reorder_skills(resume, analysis)
        original_text = _render_skills(original)
        proposed_text = _render_skills(reordered)
        if proposed_text != original_text:
            verification = verify_skill_reorder(
                [keyword for group in original for keyword in group.keywords],
                [keyword for group in reordered for keyword in group.keywords],
            )
            verifier.checked += 1
            if verification.verified:
                proposals.append(
                    _proposal(
                        kind="reorder_skills",
                        section="skills",
                        target_ref="skills",
                        original=original_text,
                        proposed=proposed_text,
                        rationale=(
                            "Order skills so the JD's must-have terms appear first. "
                            "Nothing is added or removed."
                        ),
                        keywords=[item.canonical for item in analysis.must_have][:10],
                    )
                )
            else:
                verifier.rejected += 1
                verifier.reasons.extend(verification.reasons)

    if options.suggest_metrics:
        weak = report.breakdown.impact.model_extra or {}
        assessments = weak.get("assessments", []) if isinstance(weak, dict) else []
        for assessment in assessments[:5]:
            if not isinstance(assessment, dict) or assessment.get("points") is None:
                continue
            if not isinstance(assessment.get("issues"), list):
                continue
            if not any("measurable" in issue for issue in assessment["issues"]):
                continue
            excerpt = str(assessment.get("excerpt") or "")
            if not excerpt:
                continue
            bullet_id = None
            for ref, text in _iter_bullet_refs(resume):
                if text.startswith(excerpt[:40]):
                    bullet_id = ref
                    break
            if not bullet_id:
                continue
            proposals.append(
                _proposal(
                    kind="placeholder_metric",
                    section="experience",
                    target_ref=bullet_id,
                    original=excerpt,
                    proposed=(
                        excerpt
                        + " [ADD METRIC: quantify scale, % improvement, or time saved]"
                    ),
                    rationale=(
                        "This bullet has no measurable result. The placeholder asks for a real "
                        "number instead of inventing one."
                    ),
                    truthfulness="needs_user_input",
                    risk="medium",
                )
            )

        for skill in (report.breakdown.keyword_match.model_extra or {}).get(
            "missing_must_have", []
        )[:5]:
            proposals.append(
                _proposal(
                    kind="missing_skill_question",
                    section="skills",
                    target_ref=f"missing_skill:{skill}",
                    original="",
                    proposed="",
                    rationale=(
                        f"The JD requires {skill}, but the resume shows no evidence. "
                        f"If you genuinely used {skill}, add a fact with evidence to the Facts "
                        "Bank. This engine will not insert it for you."
                    ),
                    truthfulness="needs_user_input",
                    risk="high",
                )
            )

    for issue in document.issues:
        fix = _PARSE_FIXES.get(issue.code)
        if not fix:
            continue
        proposals.append(
            _proposal(
                kind="parse_fix",
                section="format",
                target_ref=issue.code,
                original=issue.message,
                proposed=fix,
                rationale="Fix parseability before optimising wording.",
                truthfulness="verified",
            )
        )

    for ref, text in _iter_bullet_refs(resume):
        if len([p for p in proposals if p.kind == "rewrite_bullet"]) >= 6:
            break
        rewrite = _rewrite_bullet(text)
        if not rewrite:
            continue
        weak_phrase, rewritten = rewrite
        if rewritten.lower() == text.lower():
            continue
        verification = verify_rewrite(text, rewritten, [])
        verifier.checked += 1
        if verification.verified:
            proposals.append(
                _proposal(
                    kind="rewrite_bullet",
                    section="experience",
                    target_ref=ref,
                    original=text,
                    proposed=rewritten,
                    rationale=f"Replaces the weak phrase '{weak_phrase}' with a past-tense action verb.",
                )
            )
        else:
            verifier.rejected += 1
            verifier.reasons.extend(verification.reasons)

    return proposals, verifier


async def _plan_llm(
    document: ResumeDocument, analysis: JDAnalysis, facts: list[str]
) -> tuple[list[ChangeProposal], VerifierSummary]:
    verifier = VerifierSummary()
    provider = get_llm_provider()
    if provider.name == "stub":
        return [], verifier

    resume_json = json.dumps(document.canonical.model_dump(), indent=1)[:12_000]
    jd_json = json.dumps(analysis.model_dump(exclude={"analyzed_at"}), indent=1)[:6_000]
    user_prompt = (
        f"<resume>{resume_json}</resume>\n"
        f"<jd>{jd_json}</jd>\n"
        f"<facts_bank>{json.dumps(facts)}</facts_bank>"
    )
    response = await provider.complete_json(
        system=REWRITER_SYSTEM_PROMPT, user=user_prompt, schema_name="rewrite_proposals"
    )
    if not response:
        return [], verifier

    proposals: list[ChangeProposal] = []
    refs = dict(_iter_bullet_refs(document.canonical))
    for item in response.get("proposals", [])[:10]:
        if not isinstance(item, dict):
            continue
        bullet_id = str(item.get("bullet_id") or "")
        original = str(item.get("original") or refs.get(bullet_id, ""))
        rewritten = str(item.get("rewritten") or "")
        if not original or not rewritten:
            continue
        verification = verify_rewrite(original, rewritten, facts)
        verifier.checked += 1
        if not verification.verified:
            verifier.rejected += 1
            verifier.reasons.extend(verification.reasons)
            continue
        proposals.append(
            _proposal(
                kind="rewrite_bullet",
                section="experience",
                target_ref=bullet_id or None,
                original=original,
                proposed=rewritten,
                rationale="LLM rewrite, verified against the resume and Facts Bank.",
                evidence=item.get("evidence_spans", [])[:5],
                keywords=item.get("jd_keywords_used", [])[:8],
                risk="medium",
            )
        )
    return proposals, verifier


def _apply(
    document: ResumeDocument,
    proposals: list[ChangeProposal],
    analysis: JDAnalysis,
) -> ResumeDocument:
    updated = document.model_copy(deep=True)
    resume = updated.canonical

    rewrite_map = {
        proposal.original: proposal.proposed
        for proposal in proposals
        if proposal.kind == "rewrite_bullet"
    }
    for work in resume.work:
        work.highlights = [rewrite_map.get(highlight, highlight) for highlight in work.highlights]
    for project in resume.projects:
        project.highlights = [
            rewrite_map.get(highlight, highlight) for highlight in project.highlights
        ]

    if any(proposal.kind == "reorder_skills" for proposal in proposals):
        _, reordered = _reorder_skills(resume, analysis)
        resume.skills = reordered

    fix_codes = {
        proposal.target_ref for proposal in proposals if proposal.kind == "parse_fix"
    }
    updated.issues = [issue for issue in updated.issues if issue.code not in fix_codes]
    return updated


def apply_proposals(
    document: ResumeDocument, proposals: list[ChangeProposal], analysis: JDAnalysis
) -> ResumeDocument:
    """Public wrapper used when a user accepts changes after the job finished."""

    accepted = [proposal for proposal in proposals if proposal.status == "accepted"]
    return _apply(document, accepted, analysis)


async def run_optimisation(
    *,
    job_id: str,
    document: ResumeDocument,
    analysis: JDAnalysis,
    baseline: ScoreReport,
    facts: list[str],
    options: OptimiseOptions,
    target_score: float | None = None,
) -> OptimiseResult:
    target = min(target_score or options.target_score, 100.0)
    verifier = VerifierSummary()
    proposals: list[ChangeProposal] = []
    seen: set[tuple[str, str | None, str]] = set()
    current_document = document
    current_report = baseline
    iterations = 0
    stopped: str = "max_iterations"

    for iteration in range(1, options.max_iterations + 1):
        iterations = iteration
        candidates, iteration_verifier = _plan_deterministic(
            current_document, analysis, current_report, options
        )
        try:
            llm_candidates, llm_verifier = await _plan_llm(current_document, analysis, facts)
            candidates.extend(llm_candidates)
            verifier.checked += llm_verifier.checked
            verifier.rejected += llm_verifier.rejected
            verifier.needs_user_input += llm_verifier.needs_user_input
            verifier.reasons.extend(llm_verifier.reasons)
        except Exception:  # pragma: no cover - provider/network failure
            logger.exception("LLM planning failed; continuing deterministically")

        verifier.checked += iteration_verifier.checked
        verifier.rejected += iteration_verifier.rejected
        verifier.reasons.extend(iteration_verifier.reasons)

        new_candidates = []
        for candidate in candidates:
            key = (candidate.kind, candidate.target_ref, candidate.proposed)
            if key in seen:
                continue
            seen.add(key)
            new_candidates.append(candidate)

        if not new_candidates:
            stopped = "no_further_gains"
            break

        remaining = options.max_changes - len(proposals)
        proposals.extend(new_candidates[:remaining])
        if len(proposals) >= options.max_changes:
            stopped = "max_iterations"
            break

        applied = [proposal for proposal in proposals if proposal.truthfulness == "verified"]
        current_document = _apply(document, applied, analysis)
        current_report = build_score_report(
            resume_id=baseline.resume_id,
            jd_id=baseline.jd_id,
            document=current_document,
            analysis=analysis,
        )

        if current_report.overall_score >= target:
            stopped = "target_reached"
            break

    verifier.needs_user_input = sum(
        1 for proposal in proposals if proposal.truthfulness == "needs_user_input"
    )
    notes: list[str] = []
    if any(proposal.kind == "missing_skill_question" for proposal in proposals):
        notes.append(
            "Missing must-haves are surfaced as questions, not inserted. Add real evidence "
            "to the Facts Bank before claiming them."
        )
    if not any(proposal.truthfulness == "verified" for proposal in proposals):
        notes.append("No verified changes were available for this resume/JD pair.")

    return OptimiseResult(
        job_id=job_id,
        resume_id=baseline.resume_id,
        jd_id=baseline.jd_id,
        baseline_score=baseline.overall_score,
        target_score=target,
        score_after_accepted=current_report.overall_score,
        iterations=iterations,
        stopped_reason=stopped,  # type: ignore[arg-type]
        proposals=proposals,
        verifier=verifier,
        notes=notes,
        model_versions={
            "scoring": "scoring-v1",
            "optimiser": "deterministic-optimiser-v1",
            "prompt": PROMPT_VERSION if get_llm_provider().name != "stub" else "n/a",
            "llm_provider": get_llm_provider().name,
            "llm_model": settings.llm_model if get_llm_provider().name != "stub" else "n/a",
        },
    )
