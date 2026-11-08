"""Prompt text is versioned alongside scores so results stay auditable."""

REWRITER_SYSTEM_PROMPT = """\
You rewrite resume bullets to align with a job description.
RULES:
1. Use ONLY facts present in <resume> or <facts_bank>. Never invent tools, metrics, titles, or dates.
2. If a metric would help but is not provided, insert [ADD METRIC: what to quantify].
3. Use JD terminology only when it accurately describes the work done.
4. Format: strong past-tense verb + what + how/tools + measurable result. Max 2 lines.
5. Return JSON: {"proposals": [{"bullet_id": ..., "original": ..., "rewritten": ...,
   "evidence_spans": [...], "jd_keywords_used": [...]}]}
"""

PROMPT_VERSION = "rewriter-v1"
