"""
Inspect AI evaluation harness for the OpenWallyCrew pipeline.

Usage:
    inspect eval eval/pipeline_eval.py --model anthropic/claude-sonnet-4-6

Each task runs the full CrewAI pipeline against a sample project spec and
scores the outputs for completeness, security coverage, and UAT verdict.
"""
import subprocess
import tempfile
from pathlib import Path

from inspect_ai import Task, task, eval as inspect_eval
from inspect_ai.dataset import Sample, MemoryDataset
from inspect_ai.scorer import Score, Scorer, Target, accuracy, scorer
from inspect_ai.solver import Generate, Solver, TaskState, solver

from eval.scorers import (
    requirements_completeness_scorer,
    security_coverage_scorer,
    uat_verdict_scorer,
    pytest_pass_rate_scorer,
    npm_build_scorer,
)

# ── Sample specs used for evaluation ─────────────────────────────────────────

EVAL_SPECS: list[dict[str, str]] = [
    {
        "id": "url-shortener",
        "input": "Build a URL shortener service with analytics. Users paste a long URL and get a short code. Clicks are tracked per short URL.",
        "target": "go",  # expected UAT verdict
    },
    {
        "id": "cli-todo",
        "input": "Build a command-line to-do list manager in Python. Users can add, complete, delete, and list tasks. Data persists between runs.",
        "target": "go",
    },
    {
        "id": "api-rate-limiter",
        "input": "Implement a configurable rate-limiting middleware for a FastAPI application. Support per-IP and per-API-key limits with Redis as the backing store.",
        "target": "go",
    },
]


def _build_dataset() -> MemoryDataset:
    return MemoryDataset(
        samples=[
            Sample(
                input=spec["input"],
                target=spec["target"],
                id=spec["id"],
            )
            for spec in EVAL_SPECS
        ]
    )


# ── Solver: run the CrewAI pipeline and return all outputs ────────────────────

@solver
def run_pipeline() -> Solver:
    async def _solve(state: TaskState, generate: Generate) -> TaskState:
        spec = state.input_text

        # Use mkdtemp (not TemporaryDirectory) so the project persists for scorers.
        tmpdir = tempfile.mkdtemp()
        projects_dir = Path(tmpdir) / "projects"

        result = subprocess.run(
            ["openwally", "run", "--spec", spec, "--output-dir", str(projects_dir)],
            capture_output=True,
            text=True,
            cwd=tmpdir,
            timeout=600,
        )

        project_dirs = sorted(projects_dir.iterdir()) if projects_dir.exists() else []
        project_dir = str(project_dirs[0]) if project_dirs else ""
        state.metadata["project_dir"] = project_dir
        state.metadata["tmp_dir"] = tmpdir

        artifacts: dict[str, str] = {}
        docs_dir = Path(project_dir) / ".harness-docs" if project_dir else None
        if docs_dir and docs_dir.exists():
            for f in sorted(docs_dir.glob("*.md")):
                artifacts[f.name] = f.read_text(encoding="utf-8")

        combined = "\n\n---\n\n".join(
            f"## {name}\n\n{content}" for name, content in artifacts.items()
        )
        state.output.completion = combined or result.stdout or result.stderr
        return state

    return _solve


# ── Evaluation tasks ──────────────────────────────────────────────────────────

@task
def eval_requirements_completeness() -> Task:
    """Does the PM produce a spec with all required sections and numbered FRs?"""
    return Task(
        dataset=_build_dataset(),
        solver=[run_pipeline()],
        scorer=requirements_completeness_scorer(),
    )


@task
def eval_security_coverage() -> Task:
    """Does the security architect produce STRIDE threats and numbered SRs?"""
    return Task(
        dataset=_build_dataset(),
        solver=[run_pipeline()],
        scorer=security_coverage_scorer(),
    )


@task
def eval_uat_verdict() -> Task:
    """Does the pipeline reach a GO verdict in the UAT report?"""
    return Task(
        dataset=_build_dataset(),
        solver=[run_pipeline()],
        scorer=uat_verdict_scorer(),
    )


@task
def eval_pytest_pass_rate() -> Task:
    """What fraction of generated tests pass when pytest runs against the generated project?"""
    return Task(
        dataset=_build_dataset(),
        solver=[run_pipeline()],
        scorer=pytest_pass_rate_scorer(),
    )


@task
def eval_npm_build() -> Task:
    """Does the generated frontend build successfully with npm run build?"""
    return Task(
        dataset=_build_dataset(),
        solver=[run_pipeline()],
        scorer=npm_build_scorer(),
    )


def run_eval() -> None:
    inspect_eval(
        [
            eval_requirements_completeness(),
            eval_security_coverage(),
            eval_uat_verdict(),
            eval_pytest_pass_rate(),
            eval_npm_build(),
        ],
        model="anthropic/claude-sonnet-4-6",
    )


if __name__ == "__main__":
    run_eval()
