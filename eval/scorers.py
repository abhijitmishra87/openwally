"""
Custom Inspect AI scorers for evaluating OpenWallyCrew pipeline output quality.
Each scorer targets a specific pipeline stage and uses pattern matching +
model-graded evaluation for nuanced quality assessment.
"""
import re
import subprocess
from pathlib import Path

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


# ── pytest pass rate ──────────────────────────────────────────────────────────

@scorer(metrics=[mean()])
def pytest_pass_rate_scorer() -> Scorer:
    """
    Runs pytest against the generated project's test suite.
    Score = passing_tests / total_tests. Returns 0.5 if pytest cannot run.
    """
    async def score(state: TaskState, target: Target) -> Score:
        project_dir = state.metadata.get("project_dir", "")
        if not project_dir or not Path(project_dir).exists():
            return Score(value=0.5, explanation="Project directory not available for pytest")

        deps_file = Path(project_dir) / "deps.txt"
        with_flags: list[str] = ["--with", "pytest", "--with", "pytest-asyncio", "--with", "httpx"]
        if deps_file.exists():
            for line in deps_file.read_text(encoding="utf-8").splitlines():
                pkg = line.strip()
                if pkg and not pkg.startswith("#"):
                    with_flags += ["--with", pkg]

        result = subprocess.run(
            ["uv", "run"] + with_flags + ["pytest", "tests/", "--tb=no", "-q", "--no-header"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip()

        passed = len(re.findall(r"\bpassed\b", output))
        failed = len(re.findall(r"\bfailed\b", output))
        error = len(re.findall(r"\berror\b", output, re.IGNORECASE))
        total = passed + failed + error

        if total == 0:
            return Score(value=0.5, explanation=f"Could not parse pytest output: {output[:300]}")

        value = round(passed / total, 3)
        return Score(
            value=value,
            explanation=f"{passed} passed, {failed} failed, {error} errors out of {total} total",
        )

    return score


# ── npm build success ─────────────────────────────────────────────────────────

@scorer(metrics=[mean()])
def npm_build_scorer() -> Scorer:
    """
    Runs npm install + npm run build in the generated project's frontend/ directory.
    Score 1.0 for success, 0.0 for failure, 0.5 if frontend is absent.
    """
    async def score(state: TaskState, target: Target) -> Score:
        project_dir = state.metadata.get("project_dir", "")
        frontend_dir = Path(project_dir) / "frontend" if project_dir else None

        if not frontend_dir or not (frontend_dir / "package.json").exists():
            return Score(value=0.5, explanation="No frontend/package.json — frontend may not be required")

        install = subprocess.run(
            ["npm", "install", "--silent", "--no-audit", "--no-fund"],
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if install.returncode != 0:
            return Score(value=0.0, explanation=f"npm install failed: {(install.stdout + install.stderr)[:300]}")

        build = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )

        if build.returncode == 0:
            return Score(value=1.0, explanation="npm run build succeeded")

        output = (build.stdout + build.stderr).strip()
        return Score(value=0.0, explanation=f"npm run build failed: {output[:300]}")

    return score
