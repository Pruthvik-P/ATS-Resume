from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.jd import JDAnalysis
from app.schemas.resume import ResumeDocument
from app.schemas.score import (
    CapApplied,
    ComponentScore,
    PenaltyApplied,
    Recommendation,
    ScoreBreakdown,
    ScoreReport,
)
from app.services.scoring.calibration import (
    FEATURE_NAMES,
    CalibrationModel,
    load_calibration,
)
from app.services.scoring.education import score_education
from app.services.scoring.experience import score_experience
from app.services.scoring.fairness import scoring_view
from app.services.scoring.impact import score_impact
from app.services.scoring.keyword import score_keywords
from app.services.scoring.parseability import score_parseability
from app.services.scoring.readability import score_readability
from app.services.scoring.semantic import score_semantics
from app.services.text import tokenize
from app.services.versioning import SCORING_ENGINE_VERSION, scoring_model_versions
from app.taxonomy.skills import canonical_skills

logger = get_logger(__name__)


def _calibration_details(
    breakdown: ScoreBreakdown,
) -> tuple[dict[str, object], CalibrationModel | None]:
    if not settings.calibration_enabled or not settings.calibration_path:
        return {}, None
    try:
        model = load_calibration(settings.calibration_path)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning(
            "Calibration model unavailable; leaving the deterministic score unchanged",
            extra={"path": settings.calibration_path, "error": str(exc)},
        )
        return {}, None
    features = [
        breakdown.keyword_match.score,
        breakdown.semantic_relevance.score,
        breakdown.experience_fit.score,
        breakdown.parseability.score,
        breakdown.impact.score,
        breakdown.education.score,
        breakdown.readability.score,
    ]
    probability = model.predict_proba(features)
    return (
        {
            "version": model.version,
            "features": dict(zip(FEATURE_NAMES, features, strict=False)),
            "probability": round(probability, 4),
            "blend_weight": max(0.0, min(1.0, settings.calibration_blend_weight)),
        },
        model,
    )


def grade_for(score: float) -> str:
    if score >= 85:
        return "Strong - likely to pass this screen"
    if score >= 70:
        return "Good - likely to pass with targeted improvements"
    if score >= 55:
        return "Fair - gaps will filter you out at many companies"
    return "Weak - parsing and/or match gaps are likely to reject this"


def _keyword_stuffing(resume_document: ResumeDocument) -> tuple[float, list[str]]:
    resume = resume_document.canonical
    text = " ".join(
        filter(
            None,
            [
                resume.basics.summary or "",
                *[highlight for work in resume.work for highlight in work.highlights],
                *[
                    " ".join([group.name or "", *group.keywords])
                    for group in resume.skills
                ],
            ],
        )
    )
    words = tokenize(text)
    reasons: list[str] = []
    if not words:
        return 0.0, reasons

    known = {skill.lower() for skill in canonical_skills()}
    mentions = sum(1 for word in words if word in known)
    density = mentions / len(words)
    penalty = 0.0
    if density > 0.12:
        penalty += min(settings.keyword_stuffing_penalty, (density - 0.12) * 400)
        reasons.append(
            f"Skill-term density is {density:.0%} of resume text, which reads as keyword stuffing."
        )

    keywords = [keyword.lower() for group in resume.skills for keyword in group.keywords]
    duplicates = len(keywords) - len(set(keywords))
    if duplicates > 3:
        penalty += min(6.0, duplicates * 0.8)
        reasons.append(f"{duplicates} duplicate skills-list entries detected.")

    hidden_text = any(
        issue.code in {"letter_spacing", "private_use_glyphs"}
        and issue.severity == "error"
        for issue in resume_document.issues
    )
    if hidden_text:
        penalty += settings.keyword_stuffing_penalty
        reasons.append("Hidden or white text was detected; this is treated as gaming the screen.")

    return round(min(penalty, settings.keyword_stuffing_penalty + 6), 2), reasons


def _recommendations(
    keyword_details: dict,
    semantic_details: dict,
    parse_details: dict,
    impact_details: dict,
    readability_details: dict,
    analysis: JDAnalysis,
) -> list[Recommendation]:
    recommendations: list[Recommendation] = []

    missing_must = keyword_details.get("missing_must_have", [])
    if missing_must:
        recommendations.append(
            Recommendation(
                priority="high",
                type="missing_skill",
                component="keyword_match",
                text=(
                    "The JD treats these as must-haves and no evidence was found: "
                    + ", ".join(missing_must)
                    + ". Add them only if you genuinely have that experience; "
                    "otherwise this requirement is a real gap."
                ),
                evidence=list(missing_must),
            )
        )

    parse_issues = parse_details.get("issues", [])
    if parse_issues:
        recommendations.append(
            Recommendation(
                priority="high",
                type="parse_fix",
                component="parseability",
                text=(
                    "Fix these parsing problems before anything else: "
                    + "; ".join(str(issue) for issue in parse_issues[:3])
                ),
                evidence=[str(issue) for issue in parse_issues[:5]],
            )
        )

    weak = impact_details.get("weak_bullets", [])
    if weak:
        recommendations.append(
            Recommendation(
                priority="medium",
                type="impact",
                component="impact",
                text=(
                    "These bullets have no measurable result or weak structure: "
                    + ", ".join(f"#{index}" for index in weak[:8])
                    + ". Add a real metric (scale, %, time saved) or insert "
                    "[ADD METRIC: ...] for the user to fill in."
                ),
                evidence=[f"bullet {index}" for index in weak[:8]],
            )
        )

    action_ratio = impact_details.get("action_verb_ratio")
    if isinstance(action_ratio, (int, float)) and action_ratio < 0.5:
        recommendations.append(
            Recommendation(
                priority="medium",
                type="bullet_quality",
                component="impact",
                text="Fewer than half of bullets start with a strong action verb.",
            )
        )

    unmatched = semantic_details.get("unmatched_requirements", [])
    if unmatched:
        recommendations.append(
            Recommendation(
                priority="medium",
                type="semantic_gap",
                component="semantic_relevance",
                text=(
                    "These JD responsibilities have no closely matching evidence in your resume. "
                    "Reframe existing work rather than inventing experience: "
                    + "; ".join(str(item)[:120] for item in unmatched[:3])
                ),
                evidence=[str(item) for item in unmatched[:3]],
            )
        )

    missing_nice = keyword_details.get("missing_nice_to_have", [])
    if missing_nice:
        recommendations.append(
            Recommendation(
                priority="low",
                type="missing_skill",
                component="keyword_match",
                text="Nice-to-have skills not mentioned: " + ", ".join(missing_nice) + ".",
                evidence=list(missing_nice),
            )
        )

    notes = readability_details.get("notes", [])
    for note in notes[:2]:
        recommendations.append(
            Recommendation(
                priority="low",
                type="readability",
                component="readability",
                text=str(note),
            )
        )

    if analysis.knockouts:
        unverified = [
            knockout.text
            for knockout in analysis.knockouts
            if knockout.kind != "degree"
        ]
        if unverified:
            recommendations.append(
                Recommendation(
                    priority="high",
                    type="knockout_unverified",
                    text=(
                        "The JD contains eligibility language this engine cannot verify: "
                        + " | ".join(unverified[:3])
                        + ". Confirm work authorization, location, and clearance yourself."
                    ),
                )
            )

    order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda item: order[item.priority])
    return recommendations[:12]


def build_score_report(
    resume_id: str,
    jd_id: str,
    document: ResumeDocument,
    analysis: JDAnalysis,
) -> ScoreReport:
    weights = settings.scoring_weights
    fairness = scoring_view(document.canonical)
    resume = fairness.resume

    keyword, keyword_details = score_keywords(resume, analysis)
    semantic, semantic_details = score_semantics(resume, analysis)
    experience, experience_details = score_experience(resume, analysis)
    parseability, parse_details = score_parseability(document)
    impact, impact_details = score_impact(resume)
    education, education_details = score_education(resume, analysis)
    readability, readability_details = score_readability(resume)

    breakdown = ScoreBreakdown(
        keyword_match=ComponentScore(
            score=keyword.score, weight=weights.keyword_match, **keyword_details
        ),
        semantic_relevance=ComponentScore(
            score=semantic.score, weight=weights.semantic_relevance, **semantic_details
        ),
        experience_fit=ComponentScore(
            score=experience.score, weight=weights.experience_fit, **experience_details
        ),
        parseability=ComponentScore(
            score=parseability.score, weight=weights.parseability, **parse_details
        ),
        impact=ComponentScore(score=impact.score, weight=weights.impact, **impact_details),
        education=ComponentScore(
            score=education.score, weight=weights.education, **education_details
        ),
        readability=ComponentScore(
            score=readability.score, weight=weights.readability, **readability_details
        ),
    )

    raw_score = (
        keyword.score * weights.keyword_match
        + semantic.score * weights.semantic_relevance
        + experience.score * weights.experience_fit
        + parseability.score * weights.parseability
        + impact.score * weights.impact
        + education.score * weights.education
        + readability.score * weights.readability
    )

    caps: list[CapApplied] = []
    knockouts: list[str] = []

    if keyword.missing_must_have:
        caps.append(
            CapApplied(
                code="missing_must_have",
                reason="Missing a hard must-have requirement: "
                + ", ".join(keyword.missing_must_have),
                cap=settings.must_have_cap,
            )
        )
        knockouts.extend(
            f"Missing must-have: {skill}" for skill in keyword.missing_must_have
        )

    if parseability.score < settings.parse_fidelity_floor:
        caps.append(
            CapApplied(
                code="low_parse_fidelity",
                reason=(
                    f"Parse fidelity is {parseability.score:.0f}, below the "
                    f"{settings.parse_fidelity_floor:.0f} floor."
                ),
                cap=settings.parse_fidelity_cap,
            )
        )
        knockouts.append("Resume is likely to parse incorrectly in common ATS vendors.")

    capped = min([raw_score, *[cap.cap for cap in caps]]) if caps else raw_score

    penalty_points, penalty_reasons = _keyword_stuffing(document)
    penalties = [
        PenaltyApplied(code="keyword_stuffing", reason=reason, points=penalty_points)
        for reason in penalty_reasons
    ]
    overall = max(0.0, min(100.0, capped - penalty_points))

    report = ScoreReport(
        resume_id=resume_id,
        jd_id=jd_id,
        overall_score=round(overall, 1),
        raw_score=round(raw_score, 1),
        grade=grade_for(overall),
        breakdown=breakdown,
        knockouts=knockouts,
        caps=caps,
        penalties=penalties,
        recommendations=_recommendations(
            keyword_details,
            semantic_details,
            parse_details,
            impact_details,
            readability_details,
            analysis,
        ),
        parse_fidelity={
            "score": parseability.score,
            "field_recall": parseability.field_recall,
            "missing_fields": parseability.missing_fields,
            "issues": parseability.issues,
        },
        fairness=fairness.audit if settings.fairness_redaction_enabled else {},
        weights=weights.as_dict(),
        scoring_version=SCORING_ENGINE_VERSION,
        model_versions=scoring_model_versions(document, analysis),
    )
    calibration, model = _calibration_details(breakdown)
    if calibration:
        report.calibration = calibration
        report.model_versions["calibration"] = str(calibration["version"])
        weight = float(calibration["blend_weight"])
        if model is not None and weight > 0:
            ceiling = min((cap.cap for cap in report.caps), default=100.0)
            blended = (1 - weight) * report.overall_score + weight * (
                float(calibration["probability"]) * 100
            )
            report.overall_score = round(max(0.0, min(ceiling, blended)), 1)
            report.grade = grade_for(report.overall_score)
            calibration["score_after_calibration"] = report.overall_score
    return report
