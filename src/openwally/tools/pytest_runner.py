from pathlib import Path
import subprocess
from crewai.tools import BaseTool


class PytestRunnerTool(BaseTool):
    name: str = "run_pytest"
    description: str = (
        "Run the pytest test suite in the generated project. "
        "Returns a summary of passing and failing tests with failure tracebacks. "
        "Call this after writing source files to validate your implementation."
    )
    project_dir: str = ""

    def _run(self, args: str = "") -> str:
        project_path = Path(self.project_dir)

        if not project_path.exists():
            return f"Error: project directory not found at {self.project_dir}"

        tests_dir = project_path / "tests"
        if not tests_dir.exists():
            return "No tests/ directory found — write test files first before running pytest."

        deps_file = project_path / "deps.txt"
        with_flags: list[str] = ["--with", "pytest", "--with", "pytest-asyncio", "--with", "httpx"]
        if deps_file.exists():
            for line in deps_file.read_text(encoding="utf-8").splitlines():
                pkg = line.strip()
                if pkg and not pkg.startswith("#"):
                    with_flags += ["--with", pkg]

        result = subprocess.run(
            ["uv", "run"] + with_flags + ["pytest", "tests/", "--tb=short", "-q", "--no-header"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = (result.stdout + result.stderr).strip()
        if len(output) > 8000:
            output = output[:8000] + "\n... (output truncated)"

        return output or "pytest produced no output"
