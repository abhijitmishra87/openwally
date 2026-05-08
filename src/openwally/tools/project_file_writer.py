import os
from pathlib import Path
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class WriteProjectFileInput(BaseModel):
    relative_path: str = Field(
        description=(
            "Path of the file relative to the project root. "
            "Examples: 'src/myapp/main.py', 'tests/test_main.py', 'deps.txt'"
        )
    )
    content: str = Field(description="Complete file content — no placeholders, no ellipsis.")


class ProjectFileWriterTool(BaseTool):
    name: str = "write_project_file"
    description: str = (
        "Write a source file into the generated project directory. "
        "Use this for every Python module, test file, config file, and deps.txt. "
        "Call once per file — do not combine multiple files into one call."
    )
    args_schema: type[BaseModel] = WriteProjectFileInput
    project_dir: str = ""

    def _run(self, relative_path: str, content: str) -> str:
        target = Path(self.project_dir) / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Written: {target}"
