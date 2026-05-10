from pathlib import Path
from crewai.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field


class ReadArtifactInput(BaseModel):
    file_name: str = Field(
        description="Name of the pipeline document to read, e.g. '2_architecture.md'"
    )


class ArtifactReaderTool(BaseTool):
    name: str = "read_artifact"
    description: str = (
        "Read a pipeline document produced by a prior agent (requirements, architecture, "
        "security, tasks, UI design, UAT report, etc.) from the docs folder. "
        "Use this to access prior context during revision cycles."
    )
    args_schema: type[BaseModel] = ReadArtifactInput
    docs_dir: str = ""

    def _run(self, file_name: str) -> str:
        path = Path(self.docs_dir) / file_name
        if not path.exists():
            available = [f.name for f in Path(self.docs_dir).glob("*.md")]
            logger.warning("Artifact not found: {} — available: {}", file_name, available)
            return f"File '{file_name}' not found. Available: {available}"
        content = path.read_text(encoding="utf-8")
        logger.debug("Artifact read: {} ({} chars)", file_name, len(content))
        return content
