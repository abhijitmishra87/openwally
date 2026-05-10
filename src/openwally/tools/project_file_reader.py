from pathlib import Path
from crewai.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field


class ReadProjectFileInput(BaseModel):
    path: str = Field(
        description=(
            "Relative path inside the project. "
            "Pass a file path to read its contents (e.g. 'src/myapp/main.py'). "
            "Pass a directory path or '.' to list all files recursively."
        )
    )


class ProjectFileReaderTool(BaseTool):
    name: str = "read_project_file"
    description: str = (
        "Read a source file from the generated project directory, or list all files "
        "in a directory. Use this to inspect what the developers actually wrote — "
        "cross-reference against architecture contracts, security requirements, and "
        "task definitions of done."
    )
    args_schema: type[BaseModel] = ReadProjectFileInput
    project_dir: str = ""

    def _run(self, path: str) -> str:
        target = Path(self.project_dir) / path

        if not target.exists():
            logger.warning("Project file not found: {}", path)
            # suggest what is available at the nearest existing parent
            parent = target.parent
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            available = sorted(str(p.relative_to(self.project_dir))
                               for p in parent.rglob("*") if p.is_file())[:40]
            return (
                f"Path not found: {path}\n"
                f"Available files under '{parent.relative_to(self.project_dir)}':\n"
                + "\n".join(f"  {f}" for f in available)
            )

        if target.is_dir():
            files = sorted(
                str(p.relative_to(self.project_dir))
                for p in target.rglob("*")
                if p.is_file() and not any(
                    part.startswith(".") or part == "node_modules" or part == "__pycache__"
                    for part in p.parts
                )
            )
            return f"Files in '{path}':\n" + "\n".join(f"  {f}" for f in files)

        content = target.read_text(encoding="utf-8", errors="replace")
        logger.debug("Project file read: {} ({} chars)", path, len(content))
        if len(content) > 50_000:
            return (
                f"File is large ({len(content):,} chars). First 50,000 chars shown:\n\n"
                + content[:50_000]
            )
        return content
