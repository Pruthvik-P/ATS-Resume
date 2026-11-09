"""Preview one master resume against several JDs.

This does not persist versions; it gives the user a comparison matrix before
choosing which optimisation job to run. Persistence remains the job/approval
flow so every accepted change stays auditable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.jd import JDAnalysis
from app.schemas.jobs import OptimiseOptions
from app.schemas.resume import ResumeDocument
from app.schemas.tailor import TailorProposalPreview, TailorTarget
from app.services.optimiser import run_optimisation
from app.services.scoring.engine import build_score_report


@dataclass
class TailorInput:
    jd_id: str
    title: str | None
    analysis: JDAnalysis


async def tailor_preview(
    document: ResumeDocument,
    targets: list[TailorInput],
    options: OptimiseOptions,
) -> list[TailorTarget]:
    results: list[TailorTarget] = []
    for target in targets:
        baseline = build_score_report(
            resume_id="preview",
            jd_id=target.jd_id,
            document=document,
            analysis=target.analysis,
        )
        result = await run_optimisation(
            job_id=f"preview-{target.jd_id}",
            document=document,
            analysis=target.analysis,
            baseline=baseline,
            facts=[],
            options=options,
        )
        proposals = [
            TailorProposalPreview(
                id=proposal.id,
                kind=proposal.kind,
                original=proposal.original,
                proposed=proposal.proposed,
                rationale=proposal.rationale,
                truthfulness=proposal.truthfulness,
            )
            for proposal in result.proposals
            if proposal.truthfulness == "verified"
        ][:3]
        results.append(
            TailorTarget(
                jd_id=target.jd_id,
                jd_title=target.title,
                baseline_score=round(baseline.overall_score, 1),
                proposed_score=round(result.score_after_accepted, 1),
                proposal_count=len(result.proposals),
                verified_count=sum(
                    1 for proposal in result.proposals if proposal.truthfulness == "verified"
                ),
                top_proposals=proposals,
                notes=result.notes,
            )
        )
    return results


__all__ = ["TailorInput", "tailor_preview"]
