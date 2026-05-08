"""
Custom Inspect AI scorers for evaluating OpenWallyCrew pipeline output quality.
Each scorer targets a specific pipeline stage and uses pattern matching +
model-graded evaluation for nuanced quality assessment.
"""
import re

from inspect_ai.scorer import (
    Score,
    Scorer,
    Target,
    mean,
    scorer,
)
from inspect_ai.solver import TaskState


def _extract_section(text: str, heading: str) -> str:
    pattern = rf"#{{1,3}}\s+{re.escape(heading)}(.*?)(?=#{{1,3}}\s|\Z)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


# ── Requirements completeness ─────────────────────────────────────────────────

@scorer(metrics=[mean()])
def requirements_completeness_scorer() -> Scorer:
    """
    Checks that the requirements document contains:
    - All six required sections
    - At least three numbered FRs (FR-001 pattern)
    - At least three numbered ACs (AC-FR-xxx pattern)
    """
    async def score(state: TaskState, target: Target) -> Score:
        text = state.output.completion

        required_sections = [
            "Executive Summary",
            "Goals",
            "Functional Requirements",
            "Non-Functional Requirements",
            "Acceptance Criteria",
            "Open Questions",
        ]
        section_hits = sum(1 for s in required_sections if s.lower() in text.lower())
        fr_count = len(re.findall(r"FR-\d{3}", text))
        ac_count = len(re.findall(r"AC-FR-\d{3}", text))

        section_score = section_hits / len(required_sections)
        fr_score = min(fr_count / 3, 1.0)
        ac_score = min(ac_count / 3, 1.0)
        final = (section_score + fr_score + ac_score) / 3

        return Score(
            value=round(final, 3),
            explanation=(
                f"Sections: {section_hits}/{len(required_sections)}, "
                f"FRs: {fr_count}, ACs: {ac_count}"
            ),
        )

    return score


# ── Security coverage ─────────────────────────────────────────────────────────

@scorer(metrics=[mean()])
def security_coverage_scorer() -> Scorer:
    """
    Checks that the security addendum contains:
    - At least one STRIDE category mentioned
    - At least two numbered SRs (SR-xxx pattern)
    - Risk ratings (High/Medium/Low)
    """
    STRIDE_TERMS = ["Spoofing", "Tampering", "Repudiation", "Information Disclosure",
                    "Denial of Service", "Elevation of Privilege"]

    async def score(state: TaskState, target: Target) -> Score:
        text = state.output.completion

        stride_hits = sum(1 for t in STRIDE_TERMS if t.lower() in text.lower())
        sr_count = len(re.findall(r"SR-\d{3}", text))
        has_ratings = bool(re.search(r"\b(High|Medium|Low)\b", text, re.IGNORECASE))

        stride_score = min(stride_hits / 3, 1.0)
        sr_score = min(sr_count / 2, 1.0)
        rating_score = 1.0 if has_ratings else 0.0
        final = (stride_score + sr_score + rating_score) / 3

        return Score(
            value=round(final, 3),
            explanation=(
                f"STRIDE terms: {stride_hits}/6, SRs: {sr_count}, "
                f"Risk ratings present: {has_ratings}"
            ),
        )

    return score


# ── UAT verdict ───────────────────────────────────────────────────────────────

@scorer(metrics=[mean()])
def uat_verdict_scorer() -> Scorer:
    """
    Checks that the UAT report contains a clear GO / NO-GO verdict.
    Score 1.0 for GO, 0.0 for NO-GO, 0.5 if verdict is absent (pipeline incomplete).
    """
    async def score(state: TaskState, target: Target) -> Score:
        text = state.output.completion

        go_match = re.search(r"\bGO\b", text, re.IGNORECASE)
        nogo_match = re.search(r"\bNO[- ]?GO\b", text, re.IGNORECASE)

        if nogo_match:
            value = 0.0
            explanation = "Pipeline completed with NO-GO UAT verdict"
        elif go_match:
            value = 1.0
            explanation = "Pipeline completed with GO UAT verdict"
        else:
            value = 0.5
            explanation = "UAT verdict not found — pipeline may be incomplete"

        return Score(value=value, explanation=explanation)

    return score
