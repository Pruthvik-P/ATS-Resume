from __future__ import annotations

import asyncio
import json
import re
from uuid import uuid4

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.jd import JDAnalysis
from app.schemas.jobs import (
    ChangeProposal,
    IterationRecord,
    OptimiseOptions,
    OptimiseResult,
    VerifierSummary,
)
from app.schemas.resume import Resume, ResumeDocument, SkillGroup, resume_word_count
from app.schemas.score import ScoreReport
from app.services.latex.compiler import compile_source
from app.services.latex.render import render_resume_tex
from app.services.llm.base import get_llm_provider
from app.services.llm.prompts import PROMPT_VERSION, REWRITER_SYSTEM_PROMPT
from app.services.scoring.engine import build_score_report
from app.services.text import ACTION_VERBS, split_sentences
from app.services.verifier import verify_rewrite, verify_skill_reorder
from app.services.versioning import optimiser_model_versions
from app.taxonomy.skills import canonical_for, find_skills

logger = get_logger(__name__)

_WEAK_PREFIX_RE = re.compile(
    r"^(?:responsible for|duties included|worked on|helped with|helped to|"
    r"assisted with|involved in|participated in|tasked with|in charge of|"
    r"worked as|was responsible for|were responsible for|handled|utilized|"
    r"utilised|did|made)\s+",
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
    "owning": "owned",
    "driving": "drove",
    "streamlining": "streamlined",
    "modernizing": "modernized",
    "modernising": "modernised",
    "integrating": "integrated",
    "documenting": "documented",
    "architecting": "architected",
    "instrumenting": "instrumented",
    "debugging": "debugged",
    "resolving": "resolved",
    "evaluating": "evaluated",
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


_METRIC_RE = re.compile(
    r"(?:\b\d[\d,.]*\s*(?:%|percent|x|k|m|bn|million|billion|users|customers|requests|"
    r"ms|seconds|minutes|hours|days|weeks|months|people|engineers|services|teams)\b)"
    r"|(?:\$\s?\d)|(?:\b\d[\d,.]*\b)",
    re.IGNORECASE,
)


def _bullet_relevance(text: str, analysis: JDAnalysis) -> int:
    ranks = _rank_recipe(analysis)
    keyword_score = sum(
        ranks.get(match.canonical, 0) for match in find_skills(text)
    )
    metric = 1 if _METRIC_RE.search(text) else 0
    first_word = re.match(r"\s*([A-Za-z]+)", text)
    action = 1 if first_word and first_word.group(1).lower() in ACTION_VERBS else 0
    length = 1 if 40 <= len(text) <= 220 else 0
    return keyword_score * 4 + metric * 2 + action + length


def _tailor_summary(
    resume: Resume, analysis: JDAnalysis, options: OptimiseOptions
) -> str | None:
    summary = resume.basics.summary
    if not summary:
        return None
    sentences = split_sentences(summary)
    limit = {"concise": 2, "balanced": 3, "detailed": 4}[options.tone]
    if len(sentences) <= limit:
        return None
    scored = [
        (_bullet_relevance(sentence, analysis), index, sentence)
        for index, sentence in enumerate(sentences)
    ]
    if not any(score for score, _, _ in scored):
        return None
    selected = sorted(
        sorted(scored, key=lambda item: (-item[0], item[1]))[:limit],
        key=lambda item: item[1],
    )
    proposed = " ".join(sentence for _, _, sentence in selected).strip()
    return proposed if proposed != summary else None


def _reorder_bullet_list(
    highlights: list[str], analysis: JDAnalysis
) -> list[str]:
    if len(highlights) < 2:
        return highlights
    scored = [
        (_bullet_relevance(text, analysis), index, text)
        for index, text in enumerate(highlights)
    ]
    if len({score for score, _, _ in scored}) <= 1:
        return highlights
    return [
        text
        for _, _, text in sorted(scored, key=lambda item: (-item[0], item[1]))
    ]


def _verify_reorder(original: list[str], proposed: list[str]) -> tuple[bool, list[str]]:
    if sorted(original) == sorted(proposed):
        return True, []
    return False, ["Reorder changed the bullet set instead of only its order."]


def _condense_candidates(
    resume: Resume, analysis: JDAnalysis, max_pages: float
) -> list[tuple[str, str, str]]:
    words = resume_word_count(resume)
    pages = words / 450
    if pages <= max_pages + 0.05:
        return []
    must_have = {item.canonical for item in analysis.must_have}
    candidates: list[tuple[int, str, str, int]] = []
    for ref, text in _iter_bullet_refs(resume):
        matches = {match.canonical for match in find_skills(text)}
        if matches & must_have:
            continue
        score = _bullet_relevance(text, analysis)
        candidates.append((score, ref, text, len(text.split())))
    candidates.sort(key=lambda item: (item[0], -item[3]))
    excess = max(0, words - int(max_pages * 450))
    selected: list[tuple[str, str, str]] = []
    for _score, ref, text, size in candidates[:5]:
        if excess <= 0 or len(selected) >= 3:
            break
        selected.append(
            (
                ref,
                text,
                (
                    f"Removing this {size}-word bullet trims the resume toward "
                    f"{max_pages:g} page(s); review it before accepting."
                ),
            )
        )
        excess -= size
    return selected


def _estimated_pages(resume: Resume) -> float:
    return round(resume_word_count(resume) / 450, 2)


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

    if options.tailor_summary and resume.basics.summary:
        proposed_summary = _tailor_summary(resume, analysis, options)
        if proposed_summary:
            verification = verify_rewrite(
                resume.basics.summary, proposed_summary, []
            )
            verifier.checked += 1
            if verification.verified:
                proposals.append(
                    _proposal(
                        kind="summary_tailor",
                        section="summary",
                        target_ref="basics.summary",
                        original=resume.basics.summary,
                        proposed=proposed_summary,
                        rationale=(
                            "Keep the summary sentences that mention the JD's strongest "
                            "requirements; no new claims were added."
                        ),
                        keywords=[item.canonical for item in analysis.must_have][:8],
                    )
                )
            else:
                verifier.rejected += 1
                verifier.reasons.extend(verification.reasons)

    if options.reorder_bullets:
        for work_index, work in enumerate(resume.work):
            reordered = _reorder_bullet_list(work.highlights, analysis)
            if reordered == work.highlights:
                continue
            original_text = "\n".join(work.highlights)
            proposed_text = "\n".join(reordered)
            verified, reasons = _verify_reorder(work.highlights, reordered)
            verifier.checked += 1
            if verified:
                proposals.append(
                    _proposal(
                        kind="reorder_bullets",
                        section="experience",
                        target_ref=f"work[{work_index}].highlights",
                        original=original_text,
                        proposed=proposed_text,
                        rationale=(
                            "Place the bullets with the strongest JD evidence and measurable "
                            "results first. No bullet is added or removed."
                        ),
                        keywords=[item.canonical for item in analysis.must_have][:8],
                    )
                )
            else:
                verifier.rejected += 1
                verifier.reasons.extend(reasons)

    for ref, text, rationale in _condense_candidates(
        resume, analysis, options.max_pages
    ):
        proposals.append(
            _proposal(
                kind="condense_bullets",
                section="experience",
                target_ref=ref,
                original=text,
                proposed="",
                rationale=rationale,
                truthfulness="needs_user_input",
                risk="medium",
            )
        )

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
            bullet_text = ""
            for ref, text in _iter_bullet_refs(resume):
                if text.startswith(excerpt[:40]):
                    bullet_id = ref
                    bullet_text = text
                    break
            if not bullet_id:
                continue
            proposals.append(
                _proposal(
                    kind="placeholder_metric",
                    section="experience",
                    target_ref=bullet_id,
                    original=bullet_text,
                    proposed=(
                        bullet_text
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


_BULLET_REF_RE = re.compile(r"^(work|projects)\[(\d+)\]\.highlights\[(\d+)\]$")


def _set_bullet(resume: Resume, ref: str | None, text: str) -> bool:
    """Replace one highlight by its stable ``target_ref`` path.

    Matching by the original string is not enough: a metric placeholder keeps
    the whole bullet as ``original``, and an edited proposal may no longer match
    its source text. The target reference is the source of truth.
    """

    if not ref:
        return False
    match = _BULLET_REF_RE.match(ref)
    if not match:
        return False
    section, item_index, highlight_index = match.group(1), int(match.group(2)), int(match.group(3))
    collection = resume.work if section == "work" else resume.projects
    if item_index >= len(collection):
        return False
    item = collection[item_index]
    if highlight_index >= len(item.highlights):
        return False
    item.highlights[highlight_index] = text
    return True


def _apply_bullet_reorder(
    current: list[str],
    original_lines: list[str],
    proposed_lines: list[str],
    removed_indices: set[int],
) -> list[str]:
    remaining = [
        index for index in range(len(original_lines)) if index not in removed_indices
    ]
    if len(current) != len(remaining):
        return current
    by_original_index = dict(zip(remaining, current, strict=False))
    order: list[int] = []
    used: set[int] = set()
    for line in proposed_lines:
        for index, original in enumerate(original_lines):
            if index in used or index in removed_indices or original != line:
                continue
            used.add(index)
            order.append(index)
            break
    if len(order) != len(current):
        return current
    return [by_original_index[index] for index in order]


def _apply(
    document: ResumeDocument,
    proposals: list[ChangeProposal],
    analysis: JDAnalysis,
) -> ResumeDocument:
    updated = document.model_copy(deep=True)
    resume = updated.canonical

    for proposal in proposals:
        if proposal.kind not in {"rewrite_bullet", "placeholder_metric"}:
            continue
        if _set_bullet(resume, proposal.target_ref, proposal.proposed):
            continue
        # Fallback for legacy proposals without a target_ref: replace the exact
        # original text wherever it still occurs.
        for work in resume.work:
            work.highlights = [
                proposal.proposed if highlight == proposal.original else highlight
                for highlight in work.highlights
            ]
        for project in resume.projects:
            project.highlights = [
                proposal.proposed if highlight == proposal.original else highlight
                for highlight in project.highlights
            ]

    if any(proposal.kind == "summary_tailor" for proposal in proposals):
        summary = next(
            proposal.proposed
            for proposal in proposals
            if proposal.kind == "summary_tailor"
        )
        resume.basics.summary = summary

    if any(proposal.kind == "reorder_skills" for proposal in proposals):
        _, reordered = _reorder_skills(resume, analysis)
        resume.skills = reordered

    removals: dict[str, dict[int, set[int]]] = {"work": {}, "projects": {}}
    for proposal in proposals:
        if proposal.kind != "condense_bullets" or proposal.proposed.strip():
            continue
        match = _BULLET_REF_RE.match(proposal.target_ref or "")
        if not match:
            continue
        section, item_index, highlight_index = (
            match.group(1),
            int(match.group(2)),
            int(match.group(3)),
        )
        removals[section].setdefault(item_index, set()).add(highlight_index)
    for section, items in removals.items():
        collection = resume.work if section == "work" else resume.projects
        for index, indexes in items.items():
            if index >= len(collection):
                continue
            collection[index].highlights = [
                text
                for highlight_index, text in enumerate(collection[index].highlights)
                if highlight_index not in indexes
            ]

    for proposal in proposals:
        if proposal.kind != "reorder_bullets" or not proposal.target_ref:
            continue
        match = re.match(r"^(work|projects)\[(\d+)\]\.highlights$", proposal.target_ref)
        if not match:
            continue
        collection = resume.work if match.group(1) == "work" else resume.projects
        index = int(match.group(2))
        if index >= len(collection):
            continue
        collection[index].highlights = _apply_bullet_reorder(
            collection[index].highlights,
            [line for line in proposal.original.split("\n") if line.strip()],
            [line for line in proposal.proposed.split("\n") if line.strip()],
            removals[match.group(1)].get(index, set()),
        )

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


def _compile_candidate(document: ResumeDocument) -> tuple[bool, str | None, str]:
    if not settings.latex_compile_enabled:
        return True, None, "disabled"
    result = compile_source(render_resume_tex(document), filename="resume.tex")
    if result.status in {"failed", "timeout", "rejected"}:
        detail = (result.reason or result.log or "compile failed").strip()
        return False, detail[:600], result.status
    return True, None, result.status


def _compile_guard(document: ResumeDocument) -> tuple[bool, str | None]:
    """Compile the candidate and keep the legacy two-value guard contract."""

    ok, reason, _status = _compile_candidate(document)
    return ok, reason


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
    compile_failure: str | None = None
    history: list[IterationRecord] = []

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
        iteration_start = len(proposals)
        proposals.extend(new_candidates[:remaining])
        if len(proposals) >= options.max_changes:
            stopped = "max_iterations"
            break

        applied = [proposal for proposal in proposals if proposal.truthfulness == "verified"]
        candidate_document = _apply(document, applied, analysis)
        candidate_report = build_score_report(
            resume_id=baseline.resume_id,
            jd_id=baseline.jd_id,
            document=candidate_document,
            analysis=analysis,
        )

        compiled, compile_reason, compile_status = await asyncio.to_thread(
            _compile_candidate, candidate_document
        )
        record = IterationRecord(
            iteration=iteration,
            baseline_score=round(current_report.overall_score, 1),
            candidate_score=round(candidate_report.overall_score, 1),
            score_delta=round(
                candidate_report.overall_score - current_report.overall_score, 1
            ),
            compile_status=compile_status,
            parse_fidelity_before=dict(current_report.parse_fidelity),
            parse_fidelity_after=dict(candidate_report.parse_fidelity),
            rolled_back=not compiled,
            reason=compile_reason,
        )
        history.append(record)
        if not compiled:
            # Roll back the whole iteration: none of its proposals may survive.
            del proposals[iteration_start:]
            compile_failure = compile_reason
            verifier.reasons.append(
                f"Compile guard rolled back iteration {iteration}: {compile_reason}"
            )
            stopped = "failed"
            break

        current_document = candidate_document
        current_report = candidate_report

        if current_report.overall_score >= target:
            stopped = "target_reached"
            break

    verifier.needs_user_input = sum(
        1 for proposal in proposals if proposal.truthfulness == "needs_user_input"
    )
    notes: list[str] = []
    if compile_failure:
        notes.append(
            "The last optimiser iteration was rolled back because the sandboxed "
            f"LaTeX compiler rejected it: {compile_failure}"
        )
    if any(proposal.kind == "missing_skill_question" for proposal in proposals):
        notes.append(
            "Missing must-haves are surfaced as questions, not inserted. Add real evidence "
            "to the Facts Bank before claiming them."
        )
    if not any(proposal.truthfulness == "verified" for proposal in proposals):
        notes.append("No verified changes were available for this resume/JD pair.")
    pages_before = _estimated_pages(document.canonical)
    pages_after = _estimated_pages(current_document.canonical)
    if pages_after > options.max_pages:
        notes.append(
            f"Estimated length is {pages_after:g} page(s), above the {options.max_pages:g}-page "
            "target. Review the condense suggestions."
        )

    provider = get_llm_provider()
    return OptimiseResult(
        job_id=job_id,
        resume_id=baseline.resume_id,
        jd_id=baseline.jd_id,
        baseline_score=baseline.overall_score,
        target_score=target,
        score_after_accepted=current_report.overall_score,
        estimated_pages_before=pages_before,
        estimated_pages_after=pages_after,
        iterations=iterations,
        stopped_reason=stopped,  # type: ignore[arg-type]
        proposals=proposals,
        verifier=verifier,
        notes=notes,
        iteration_history=history,
        model_versions=optimiser_model_versions(
            provider_name=provider.name,
            prompt_version=PROMPT_VERSION,
            llm_model=settings.llm_model,
        ),
    )
