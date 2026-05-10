from pathlib import Path
from crewai.tools import BaseTool
from loguru import logger
from pydantic import BaseModel, Field


class WriteArtifactInput(BaseModel):
    file_name: str = Field(description="File name, e.g. '1_requirements.md'")
    content: str = Field(description="Full markdown content to write")


class ArtifactWriterTool(BaseTool):
    name: str = "write_artifact"
    description: str = (
        "Persist a pipeline document (requirements, architecture, security, tasks, UAT report) "
        "to the docs folder. Pass a file_name and the complete markdown content."
    )
    args_schema: type[BaseModel] = WriteArtifactInput
    output_dir: str = "./output"

    def _run(self, file_name: str, content: str) -> str:
        target = Path(self.output_dir) / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.debug("Artifact written: {} ({} chars)", file_name, len(content))
        return f"Artifact written: {target}"
