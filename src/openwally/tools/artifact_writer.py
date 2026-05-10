from pathlib import Path
from crewai.tools import BaseTool
from loguru import logger


class ArtifactWriterTool(BaseTool):
    name: str = "write_artifact"
    description: str = (
        "Save your complete document to disk. "
        "Pass the ENTIRE document text as the content argument — "
        "do not omit any sections or summarise."
    )
    output_dir: str = ""
    file_name: str = ""

    def _run(self, content: str) -> str:
        if not content or not content.strip():
            return (
                "Error: content is empty. Pass your complete document text "
                "as the content argument and call this tool again."
            )
        target = Path(self.output_dir) / self.file_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.debug("Artifact written: {} ({} chars)", self.file_name, len(content))
        return f"Artifact written: {self.file_name}"
