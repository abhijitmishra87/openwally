"""
openwally run --spec-file idea.md [--mode milestone] [--max-revisions 2]
"""
import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule

from openwally.crew import (
    MODES, REVIEW_DEPTHS, _REVIEW_INSTRUCTIONS,
    BACKEND_VALIDATION_INSTRUCTIONS, FRONTEND_VALIDATION_INSTRUCTIONS,
    BACKEND_STANDARDS, FRONTEND_STANDARDS, REVIEWER_STANDARDS,
    TEAM_ROSTER,
    OpenWallyCrew, RevisionCrew,
)
from openwally.scaffolding import scaffold

load_dotenv()
console = Console()


def _slugify(text: str) -> str:
    words = re.sub(r"[^a-zA-Z0-9\s]", "", text.lower()).split()
    return "-".join(words[:5]) or "generated-project"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="openwally",
        description="Autonomously generate a software project using an AI agent pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the full pipeline")

    spec_group = run.add_mutually_exclusive_group(required=True)
    spec_group.add_argument("--spec", type=str, help="Project idea as a plain string")
    spec_group.add_argument("--spec-file", type=Path, metavar="FILE",
                            help="Path to a .md or .txt file with the project spec")

    run.add_argument("--name", type=str, default=None,
                     help="Project folder name (default: derived from spec)")
    run.add_argument("--output-dir", type=Path, default=Path("./projects"), metavar="DIR",
                     help="Parent directory for generated projects (default: ./projects)")
    run.add_argument("--mode", choices=MODES, default="autonomous",
                     help=(
                         "autonomous — fully hands-off (default); "
                         "milestone — pause after requirements, UI design, and tests; "
                         "interactive — pause after every agent"
                     ))
    run.add_argument("--max-revisions", type=int, default=2, metavar="N",
                     help="Max UAT revision cycles on NO-GO verdict (default: 2, 0 = disabled)")
    run.add_argument("--review-depth", choices=REVIEW_DEPTHS, default="standard",
                     dest="review_depth",
                     help=(
                         "off — skip code review entirely; "
                         "standard — risk-prioritised (auth, endpoints, models first) (default); "
                         "thorough — reads every source file exhaustively"
                     ))
    run.add_argument("--no-validate", action="store_true", default=False,
                     dest="no_validate",
                     help=(
                         "Skip in-pipeline validation — agents won't run pytest or npm build "
                         "to self-correct. Faster and cheaper; useful for quick iteration."
                     ))
    run.add_argument("--no-standards", action="store_true", default=False,
                     dest="no_standards",
                     help=(
                         "Skip engineering standards injection — agents won't enforce logging, "
                         "error handling, health endpoints, or env-var config. Use when you "
                         "want a bare-bones project and will apply your own standards."
                     ))

    return parser.parse_args()


def _is_go(docs_dir: Path, report_name: str) -> bool:
    report = docs_dir / report_name
    if not report.exists():
        return False
    text = report.read_text(encoding="utf-8")
    if re.search(r"\bNO[- ]?GO\b", text, re.IGNORECASE):
        return False
    return bool(re.search(r"\bGO\b", text, re.IGNORECASE))


def _mode_description(mode: str) -> str:
    return {
        "autonomous":  "Fully autonomous — no human checkpoints",
        "milestone":   "Milestone review — pauses after requirements, UI design, and tests",
        "interactive": "Interactive — pauses after every agent for your feedback",
    }[mode]


def run() -> None:
    args = _parse_args()

    if args.command != "run":
        return

    # ── Load spec ──────────────────────────────────────────────────────────────
    if args.spec_file:
        spec_path = args.spec_file.expanduser().resolve()
        if not spec_path.exists():
            console.print(f"[red]File not found:[/red] {spec_path}")
            sys.exit(1)
        if spec_path.suffix.lower() not in {".md", ".txt"}:
            console.print("[red]--spec-file must be a .md or .txt file[/red]")
            sys.exit(1)
        spec = spec_path.read_text(encoding="utf-8").strip()
    else:
        spec = args.spec.strip()

    # ── Resolve project directory ──────────────────────────────────────────────
    project_name = args.name or _slugify(spec)
    output_dir: Path = args.output_dir.expanduser().resolve()
    project_dir = output_dir / project_name

    if project_dir.exists() and any(project_dir.iterdir()):
        console.print(f"[red]Project directory already exists and is not empty:[/red] {project_dir}")
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = project_dir / ".harness-docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    validate = not args.no_validate
    standards = not args.no_standards

    # Remove the default stderr sink — Rich handles terminal output.
    # Log everything DEBUG+ to a file in the harness docs folder.
    logger.remove()
    logger.add(
        docs_dir / "openwally.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} | {message}",
        rotation="10 MB",
        retention=3,
        encoding="utf-8",
    )
    logger.info("OpenWally pipeline starting — project: {}", project_name)
    logger.info("Mode: {}  review_depth: {}  validate: {}  standards: {}  max_revisions: {}",
                args.mode, args.review_depth, validate, standards, args.max_revisions)

    console.print(Panel(spec, title="[bold cyan]Project Spec[/bold cyan]", border_style="cyan"))
    console.print(f"[bold]Project:[/bold]       {project_name}")
    console.print(f"[bold]Output:[/bold]        {project_dir}")
    console.print(f"[bold]Mode:[/bold]          [cyan]{args.mode}[/cyan] — {_mode_description(args.mode)}")
    console.print(f"[bold]Review depth:[/bold]  [cyan]{args.review_depth}[/cyan]")
    console.print(f"[bold]Validation:[/bold]    [cyan]{'on' if validate else 'off'}[/cyan]"
                  + ("" if validate else " — agents will not self-correct via pytest / npm build"))
    console.print(f"[bold]Standards:[/bold]     [cyan]{'on' if standards else 'off'}[/cyan]"
                  + ("" if standards else " — bare-bones project, no standards enforced"))
    console.print(f"[bold]Max revisions:[/bold] {args.max_revisions}\n")

    # ── Shared kickoff inputs ──────────────────────────────────────────────────
    review_instructions = _REVIEW_INSTRUCTIONS.get(args.review_depth, "")
    backend_val = BACKEND_VALIDATION_INSTRUCTIONS if validate else ""
    frontend_val = FRONTEND_VALIDATION_INSTRUCTIONS if validate else ""
    backend_std = BACKEND_STANDARDS if standards else ""
    frontend_std = FRONTEND_STANDARDS if standards else ""
    reviewer_std = REVIEWER_STANDARDS if standards else ""
    base_inputs = {
        "project_spec": spec,
        "project_name": project_name,
        "team_roster": TEAM_ROSTER,
        "review_instructions": review_instructions,
        "backend_validation_instructions": backend_val,
        "frontend_validation_instructions": frontend_val,
        "backend_standards": backend_std,
        "frontend_standards": frontend_std,
        "reviewer_standards": reviewer_std,
    }

    def _progress_bar(description: str, total: int) -> Progress:
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=28),
            TextColumn("[green]{task.completed}[/green][dim]/{task.total} agents[/dim]"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )

    # ── Main pipeline ──────────────────────────────────────────────────────────
    console.print(Rule("[bold]Pipeline — Pass 1[/bold]"))
    logger.info("Starting main pipeline (pass 1)")
    n_agents = 13 if args.review_depth == "off" else 14
    with _progress_bar("Pipeline", n_agents) as progress:
        task_id = progress.add_task("Pipeline", total=n_agents)

        def advance_main(agent_name: str) -> None:
            progress.advance(task_id)
            progress.update(task_id, description=f"Pipeline  [dim]{agent_name} ✓[/dim]")

        OpenWallyCrew(
            project_dir=project_dir,
            docs_dir=docs_dir,
            mode=args.mode,
            review_depth=args.review_depth,
            validate=validate,
            on_task_complete=advance_main,
        ).crew().kickoff(inputs=base_inputs)

    # ── UAT revision loop ──────────────────────────────────────────────────────
    uat_report = "10_uat_report.md"
    revision = 0

    while not _is_go(docs_dir, uat_report) and revision < args.max_revisions:
        revision += 1
        logger.warning("UAT NO-GO — starting revision cycle {}/{}", revision, args.max_revisions)
        console.print(Rule(
            f"[bold yellow]UAT — NO-GO · Revision {revision}/{args.max_revisions}[/bold yellow]"
        ))
        console.print(
            f"  Defects found. Running targeted fix cycle "
            f"({revision}/{args.max_revisions})...\n"
        )

        with _progress_bar(f"Revision {revision}", 4) as progress:
            task_id = progress.add_task(f"Revision {revision}", total=4)

            def advance_revision(agent_name: str) -> None:
                progress.advance(task_id)
                progress.update(task_id, description=f"Revision {revision}  [dim]{agent_name} ✓[/dim]")

            RevisionCrew(
                project_dir=project_dir,
                docs_dir=docs_dir,
                revision_num=revision,
                mode=args.mode,
                validate=validate,
                on_task_complete=advance_revision,
            ).crew().kickoff(inputs={**base_inputs, "revision_num": str(revision)})

        uat_report = f"revision_{revision}_uat_report.md"

    # ── Final verdict ──────────────────────────────────────────────────────────
    if _is_go(docs_dir, uat_report):
        logger.info("UAT verdict: GO — pipeline complete")
        console.print(Rule("[bold green]UAT — GO ✓[/bold green]"))
    else:
        logger.error("UAT verdict: NO-GO after {} revision(s) — manual fixes required", revision)
        console.print(Rule("[bold red]UAT — NO-GO after max revisions[/bold red]"))
        console.print(
            f"  [yellow]Reached revision limit ({args.max_revisions}) without a GO verdict.[/yellow]\n"
            f"  Review [cyan]{docs_dir / uat_report}[/cyan] for outstanding defects.\n"
            f"  Project files are still at [cyan]{project_dir}[/cyan] for manual fixes.\n"
        )

    # ── Scaffold regardless of verdict ────────────────────────────────────────
    scaffold(project_dir, project_name)


if __name__ == "__main__":
    run()
