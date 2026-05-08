"""
openwally run --spec-file idea.md [--mode milestone] [--max-revisions 2]
"""
import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from openwally.crew import MODES, OpenWallyCrew, RevisionCrew
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

    console.print(Panel(spec, title="[bold cyan]Project Spec[/bold cyan]", border_style="cyan"))
    console.print(f"[bold]Project:[/bold]       {project_name}")
    console.print(f"[bold]Output:[/bold]        {project_dir}")
    console.print(f"[bold]Mode:[/bold]          [cyan]{args.mode}[/cyan] — {_mode_description(args.mode)}")
    console.print(f"[bold]Max revisions:[/bold] {args.max_revisions}\n")

    # ── Main pipeline ──────────────────────────────────────────────────────────
    console.print(Rule("[bold]Pipeline — Pass 1[/bold]"))
    OpenWallyCrew(
        project_dir=project_dir,
        docs_dir=docs_dir,
        mode=args.mode,
    ).crew().kickoff(inputs={"project_spec": spec, "project_name": project_name})

    # ── UAT revision loop ──────────────────────────────────────────────────────
    uat_report = "10_uat_report.md"
    revision = 0

    while not _is_go(docs_dir, uat_report) and revision < args.max_revisions:
        revision += 1
        console.print(Rule(
            f"[bold yellow]UAT — NO-GO · Revision {revision}/{args.max_revisions}[/bold yellow]"
        ))
        console.print(
            f"  Defects found. Running targeted fix cycle "
            f"({revision}/{args.max_revisions})...\n"
        )

        RevisionCrew(
            project_dir=project_dir,
            docs_dir=docs_dir,
            revision_num=revision,
            mode=args.mode,
        ).crew().kickoff(inputs={
            "project_spec": spec,
            "project_name": project_name,
            "revision_num": str(revision),
        })

        uat_report = f"revision_{revision}_uat_report.md"

    # ── Final verdict ──────────────────────────────────────────────────────────
    if _is_go(docs_dir, uat_report):
        console.print(Rule("[bold green]UAT — GO ✓[/bold green]"))
    else:
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
