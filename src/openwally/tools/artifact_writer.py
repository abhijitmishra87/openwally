from pathlib import Path
from crewai.tools import BaseTool
from loguru import logger


class ArtifactWriterTool(BaseTool):
    name: str = "write_artifact"
    description: str = (
        "Persist a pipeline document (requirements, architecture, security, tasks, UAT report) "
        "to the docs folder. "
        "Arguments: file_name (str) — e.g. '1_requirements.md'; "
        "content (str) — the complete markdown content to write. Both are required."
    )
    output_dir: str = "./output"

    def _run(self, file_name: str, content: str) -> str:
        target = Path(self.output_dir) / file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.debug("Artifact written: {} ({} chars)", file_name, len(content))
        return f"Artifact written: {target}"
