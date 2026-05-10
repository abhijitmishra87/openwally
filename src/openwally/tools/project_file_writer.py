import os
from pathlib import Path
from crewai.tools import BaseTool
from loguru import logger


class ProjectFileWriterTool(BaseTool):
    name: str = "write_project_file"
    description: str = (
        "Write a source file into the generated project directory. "
        "Use this for every Python module, test file, config file, and deps.txt. "
        "Call once per file — do not combine multiple files into one call. "
        "Arguments: relative_path (str) — e.g. 'src/myapp/main.py'; "
        "content (str) — the complete file content. Both are required."
    )
    project_dir: str = ""

    def _run(self, relative_path: str, content: str) -> str:
        target = Path(self.project_dir) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.debug("Project file written: {} ({} chars)", relative_path, len(content))
        return f"Written: {target}"
