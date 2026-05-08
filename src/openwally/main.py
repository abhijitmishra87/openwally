"""
openwally run --spec-file idea.md
openwally run --spec "Build a URL shortener" --name url-shortener
"""
import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from openwally.crew import OpenWallyCrew
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
    spec_group.add_argument(
        "--spec-file",
        type=Path,
        metavar="FILE",
        help="Path to a .md or .txt file containing the project spec",
    )

    run.add_argument(
        "--name",
        type=str,
        default=None,
        help="Project folder name (default: derived from spec)",
    )
    run.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./projects"),
        metavar="DIR",
        help="Parent directory for generated projects (default: ./projects)",
    )

    return parser.parse_args()


def run() -> None:
    args = _parse_args()

    if args.command == "run":
        # ── Load spec ──────────────────────────────────────────────────────────
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

        # ── Resolve project directory ──────────────────────────────────────────
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
        console.print(f"[bold]Project name:[/bold] {project_name}")
        console.print(f"[bold]Output:[/bold]       {project_dir}\n")

        # ── Run the crew ───────────────────────────────────────────────────────
        result = OpenWallyCrew(
            project_dir=project_dir,
            docs_dir=docs_dir,
        ).crew().kickoff(inputs={"project_spec": spec, "project_name": project_name})

        # ── Scaffold: uv + git ─────────────────────────────────────────────────
        scaffold(project_dir, project_name)


if __name__ == "__main__":
    run()
