from pathlib import Path
from crewai.tools import BaseTool
from loguru import logger


class ProjectFileWriterTool(BaseTool):
    name: str = "write_project_file"
    description: str = (
        "Write a source file into the generated project directory. "
        "Use this for every Python module, test file, config file, and deps.txt. "
        "Call once per file — do not combine multiple files into one call. "
        "Arguments: relative_path (str) — RELATIVE to the project root, "
        "e.g. 'src/myapp/main.py' or 'tests/test_foo.py'. "
        "Do NOT pass an absolute path. Do NOT include any leading directory "
        "from the host filesystem. Just the path inside the project. "
        "content (str) — the complete file content. Both are required."
    )
    project_dir: str = ""

    def _run(self, relative_path: str, content: str = "") -> str:
        if not content:
            return (
                f"Error: 'content' argument is missing. "
                f"You must call this tool with BOTH arguments: "
                f"relative_path='{relative_path}' AND content='<complete file content>'. "
                f"Please call the tool again including the full file content."
            )

        project_root = Path(self.project_dir).resolve()
        rel = relative_path.strip()

        # Reject true absolute paths.
        if Path(rel).is_absolute():
            logger.warning("write_project_file rejected absolute path: {}", rel)
            return (
                f"Error: relative_path must be relative to the project root, "
                f"got absolute path '{rel}'. Pass something like 'src/myapp/main.py' "
                f"instead. Project root is fixed — do not include it."
            )

        # Detect "absolute path with leading slash stripped" — common LLM mistake.
        # If the relative path's prefix matches the project root's path components,
        # strip them so the file lands in the right place.
        rel_parts = Path(rel).parts
        root_parts = project_root.parts
        # Compare ignoring the leading "/" component pathlib gives on POSIX.
        root_compare = root_parts[1:] if root_parts and root_parts[0] == "/" else root_parts
        if len(rel_parts) >= len(root_compare) and rel_parts[:len(root_compare)] == root_compare:
            stripped = Path(*rel_parts[len(root_compare):])
            logger.warning(
                "write_project_file: stripped duplicated project path prefix "
                "from '{}' → '{}'", rel, stripped,
            )
            rel = str(stripped) if str(stripped) != "." else ""
            if not rel:
                return (
                    f"Error: relative_path appears to be the project root itself. "
                    f"Pass a path inside the project, e.g. 'src/myapp/main.py'."
                )

        target = (project_root / rel).resolve()

        # Final safety: refuse anything that escapes the project root.
        try:
            target.relative_to(project_root)
        except ValueError:
            logger.warning("write_project_file refused path escaping project root: {}", rel)
            return (
                f"Error: path '{relative_path}' resolves outside the project root. "
                f"Use a path relative to the project, e.g. 'src/myapp/main.py'."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.debug("Project file written: {} ({} chars)", rel, len(content))
        return f"Written: {target}"
